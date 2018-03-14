FROM ubuntu:16.04
MAINTAINER sminot@fredhutch.org

# Install prerequisites
RUN apt update && \
	apt-get install -y build-essential wget unzip python2.7 \
					   python-dev git python-pip bats awscli curl \
					   libcurl4-openssl-dev make gcc zlib1g-dev

# Set the default langage to C
ENV LC_ALL C

# Use /share as the working directory
RUN mkdir /share
WORKDIR /share

# Add files
RUN mkdir /usr/swarm
ADD requirements.txt /usr/swarm

# Install python requirements
RUN pip install -r /usr/swarm/requirements.txt && rm /usr/swarm/requirements.txt

# Install Swarm
RUN cd /usr/swarm && \
	wget https://github.com/torognes/swarm/releases/download/v2.2.2/swarm-2.2.2-linux-x86_64 && \
	chmod +x swarm-2.2.2-linux-x86_64 && \
	ln -s /usr/swarm/swarm-2.2.2-linux-x86_64 /usr/local/bin/swarm

# Run tests and then remove the folder
ADD tests /usr/swarm/tests
RUN bats /usr/swarm/tests/ && rm -r /usr/swarm/tests/

