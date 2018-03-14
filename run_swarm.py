#!/usr/bin/python
"""Wrapper script to run Swarm on a FASTQ file."""

import os
import sys
import uuid
import time
import shutil
import logging
import argparse
import traceback
import subprocess


def run_cmds(commands, retry=0, catchExcept=False, stdout=None):
    """Run commands and write out the log, combining STDOUT & STDERR."""
    logging.info("Commands:")
    logging.info(' '.join(commands))
    if stdout is None:
        p = subprocess.Popen(commands,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        stdout, stderr = p.communicate()
    else:
        with open(stdout, "wt") as fo:
            p = subprocess.Popen(commands,
                                 stderr=subprocess.PIPE,
                                 stdout=fo)
            stdout, stderr = p.communicate()
        stdout = False
    exitcode = p.wait()
    if stdout:
        logging.info("Standard output of subprocess:")
        for line in stdout.split('\n'):
            logging.info(line)
    if stderr:
        logging.info("Standard error of subprocess:")
        for line in stderr.split('\n'):
            logging.info(line)

    # Check the exit code
    if exitcode != 0 and retry > 0:
        msg = "Exit code {}, retrying {} more times".format(exitcode, retry)
        logging.info(msg)
        run_cmds(commands, retry=retry - 1)
    elif exitcode != 0 and catchExcept:
        msg = "Exit code was {}, but we will continue anyway"
        logging.info(msg.format(exitcode))
    else:
        assert exitcode == 0, "Exit code {}".format(exitcode)


def return_results(fp, output_folder, gzip=True):
    """Copy the results to the output folder."""

    # Compress the output
    if gzip:
        run_cmds(['gzip', fp])
        fp = fp + '.gz'

    if output_folder.startswith('s3://'):
        # Copy to S3
        run_cmds([
            'aws',
            's3',
            'cp',
            '--quiet',
            '--sse',
            'AES256',
            fp,
            output_folder])
    else:
        # Copy to local folder
        run_cmds(['mv', fp, output_folder])


def exit_and_clean_up(temp_folder):
    """Log the error messages and delete the temporary folder."""
    # Capture the traceback
    logging.info("There was an unexpected failure")
    exc_type, exc_value, exc_traceback = sys.exc_info()
    for line in traceback.format_tb(exc_traceback):
        logging.info(line)

    # Delete any files that were created for this sample
    logging.info("Removing temporary folder: " + temp_folder)
    shutil.rmtree(temp_folder)

    # Exit
    logging.info("Exit type: {}".format(exc_type))
    logging.info("Exit code: {}".format(exc_value))
    sys.exit(exc_value)


def get_reads_from_url(
    input_str,
    temp_folder,
):
    """Get a set of reads from a URL -- return the downloaded filepath."""
    logging.info("Getting reads from {}".format(input_str))

    filename = input_str.split('/')[-1]
    local_path = os.path.join(temp_folder, filename)

    logging.info("Filename: " + filename)
    logging.info("Local path: " + local_path)

    if not input_str.startswith((
        's3://', 'sra://',
        'ftp://', 'https://', 'http://'
    )):
        logging.info("Treating as local path")
        msg = "Input file does not exist ({})".format(input_str)
        assert os.path.exists(input_str), msg

        logging.info("Making a copy in the temporary folder")
        shutil.copyfile(input_str, local_path)

    # Get files from AWS S3
    elif input_str.startswith('s3://'):
        logging.info("Getting reads from S3")
        run_cmds([
            'aws', 's3', 'cp', '--quiet', '--sse',
            'AES256', input_str, temp_folder
            ])

    # Get files from an FTP server
    elif input_str.split('://', 1)[0] in ['ftp', 'https', 'http']:
        logging.info("Getting reads from FTP")
        run_cmds(['wget', '-P', temp_folder, input_str])

    # Get files from SRA
    elif input_str.startswith('sra://'):
        accession = filename
        logging.info("Getting reads from SRA: " + accession)
        local_path = get_sra(accession, temp_folder)

    else:
        raise Exception("Did not recognize prefix for input: " + input_str)

    # If the file is gzipped, unzip it
    if local_path.endswith(".gz"):
        logging.info("Decompressing " + local_path)
        run_cmds(["pigz", "-d", local_path])
        local_path = local_path[:-3]

    # If the file is a FASTQ, convert to FASTA
    if local_path[-1] in ["q", "Q"]:
        logging.info("Converting to FASTA")
        fasta_fp = local_path[:-1] + "a"
        run_cmds(["fastq_to_fasta", "-i", local_path, "-o", fasta_fp])
        local_path = fasta_fp

    return local_path


def set_up_sra_cache_folder(temp_folder):
    """Set up the fastq-dump cache folder within the temp folder."""
    logging.info("Setting up fastq-dump cache within {}".format(temp_folder))
    for path in [
        "/root/ncbi",
        "/root/ncbi/public"
    ]:
        if os.path.exists(path) is False:
            os.mkdir(path)

    if os.path.exists("/root/ncbi/public/sra"):
        shutil.rmtree("/root/ncbi/public/sra")

    # Now make a folder within the temp folder
    temp_cache = os.path.join(temp_folder, "sra")
    assert os.path.exists(temp_cache) is False
    os.mkdir(temp_cache)

    # Symlink it to /root/ncbi/public/sra/
    run_cmds(["ln", "-s", "-f", temp_cache, "/root/ncbi/public/sra"])

    assert os.path.exists("/root/ncbi/public/sra")


def get_sra(accession, temp_folder):
    """Get the FASTQ for an SRA accession."""

    set_up_sra_cache_folder(temp_folder)

    logging.info("Downloading {} from SRA".format(accession))

    local_path = os.path.join(temp_folder, accession + ".fastq")
    logging.info("Local path: {}".format(local_path))

    # Download via fastq-dump
    logging.info("Downloading via fastq-dump")
    run_cmds([
        "prefetch", accession
    ])
    run_cmds([
        "fastq-dump",
        "--split-files",
        "--outdir",
        temp_folder, accession
    ])

    # Make sure that some files were created
    msg = "File could not be downloaded from SRA: {}".format(accession)
    assert any([
        fp.startswith(accession) and fp.endswith("fastq")
        for fp in os.listdir(temp_folder)
    ]), msg

    # Combine any multiple files that were found
    logging.info("Concatenating output files")
    with open(local_path + ".temp", "wt") as fo:
        cmd = "cat {}/{}*fastq".format(temp_folder, accession)
        cat = subprocess.Popen(cmd, shell=True, stdout=fo)
        cat.wait()

    # Remove the temp files
    for fp in os.listdir(temp_folder):
        if fp.startswith(accession) and fp.endswith("fastq"):
            fp = os.path.join(temp_folder, fp)
            logging.info("Removing {}".format(fp))
            os.unlink(fp)

    # Remove the cache file, if any
    cache_fp = "/root/ncbi/public/sra/{}.sra".format(accession)
    if os.path.exists(cache_fp):
        logging.info("Removing {}".format(cache_fp))
        os.unlink(cache_fp)

    # Clean up the FASTQ headers for the downloaded file
    run_cmds(["mv", local_path + ".temp", local_path])

    # Return the path to the file
    logging.info("Done fetching " + accession)
    return local_path


if __name__ == "__main__":
    """Run Swarm"""

    parser = argparse.ArgumentParser(description="""
        Align a set of reads with Swarm""")

    parser.add_argument("--input",
                        type=str,
                        required=True,
                        help="""Location for input file.
                                (Supported: sra://, s3://, or ftp://).""")
    parser.add_argument("--sample-name",
                        type=str,
                        required=True,
                        help="""Name of sample, determines output filenames.""")
    parser.add_argument("--output-folder",
                        type=str,
                        required=True,
                        help="""Folder to place results.
                                (Supported: s3://, or local path).""")
    parser.add_argument("--differences",
                        type=int,
                        default=1,
                        help="Resolution parameter used by Swarm.")
    parser.add_argument("--min-mass",
                        type=int,
                        default=1,
                        help="""drop OTUs with total mass less than N
                                [default 1, ie, no dropping]
                              """)
    parser.add_argument("--keep-abundance",
                        action="store_true",
                        help="Keep abundance annotation in seed names.")
    parser.add_argument("--temp-folder",
                        type=str,
                        default='/share',
                        help="Folder used for temporary files.")

    args = parser.parse_args(sys.argv[1:])

    start_time = time.time()

    # Make a temporary folder for all files to be placed in
    temp_folder = os.path.join(args.temp_folder, str(uuid.uuid4())[:8])
    assert os.path.exists(temp_folder) is False
    os.mkdir(temp_folder)

    # Set up logging
    log_fp = os.path.join(temp_folder, "{}.log.txt".format(args.sample_name))
    logFormatter = logging.Formatter(
        '%(asctime)s %(levelname)-8s [Swarm] %(message)s'
    )
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.INFO)

    # Write to file
    fileHandler = logging.FileHandler(log_fp)
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)
    # Also write to STDOUT
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

    # Get the input file
    logging.info("Fetching input file")
    try:
        read_fps = get_reads_from_url(
            args.input, temp_folder
        )
    except:
        exit_and_clean_up(temp_folder)

    # Format the names of the output files
    fasta_out = os.path.join(
        temp_folder,
        "{}.swarm.fasta".format(args.sample_name)
    )
    csv_out = os.path.join(
        temp_folder,
        "{}.swarm.csv".format(args.sample_name)
    )
    logging.info("FASTA output: " + fasta_out)
    logging.info("CSV output: " + csv_out)

    # Format the Swarm command
    command = [
        "swarmwrapper",
        "cluster",
        read_fps,
        "-D",                            # Dereplicate
        "-w", fasta_out,                 # FASTA output
        "-a", csv_out,                   # CSV output
        "-d", str(args.differences),     # Dereplicate param
        "-M", str(args.min_mass),        # Min mass param
    ]
    if args.keep_abundance:
        command.append("--keep-abundance")

    # Run Swarm
    try:
        run_cmds(command)
    except:
        exit_and_clean_up(temp_folder)

    logging.info("Seconds elapsed: {:,}".format(time.time() - start_time))

    # Make sure the output files exist
    for fp in [fasta_out, csv_out]:
        assert os.path.exists(fp)
        assert os.stat(fp).st_size > 0

    # Now return the results
    for fp in [fasta_out, csv_out, log_fp]:
        return_results(fp, args.output_folder)
