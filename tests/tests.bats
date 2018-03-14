#!/usr/bin/env bats

@test "AWS CLI v1.11.146" {
  v="$(aws --version 2>&1)"
  [[ "$v" =~ "1.11.146" ]]
}


@test "Curl v7.47.0" {
  v="$(curl --version)"
  [[ "$v" =~ "7.47.0" ]]
}

@test "Swarm v2.2.2" {
  v="$(swarm -v 2>&1 || true )"
  [[ "$v" =~ "2.2.2" ]]
}

@test "Swarmwrapper v0.4.7" {
  v="$(swarmwrapper -V 2>&1 || true )"
  [[ "$v" =~ "0.4.7" ]]
}

@test "Swarmwrapper cluster" {
  cd /usr/swarm/tests && \
  swarmwrapper cluster seqs1000.fasta -D -w seqs1000.clusters.fasta -a seqs1000.clusters.csv

  [[ -s seqs1000.clusters.csv ]]
  [[ -s seqs1000.clusters.fasta ]]

  [[ "$(cat seqs1000.clusters.csv | wc -l)" == "340" ]]
  [[ "$(cat seqs1000.clusters.fasta | wc -l)" == "680" ]]
}

@test "run_swarm.py" {
  [[ $(run_swarm.py -h) ]]
}
