FROM debian:stable-slim as builder

LABEL org.opencontainers.image.source = "https://github.com/yjcyxky/paper-downloader"

WORKDIR /data/paper-downloader

ENV PATH="$PATH:/opt/conda/bin:/opt/conda/envs/venv/bin"
ENV FC_LANG en-US
ENV LC_CTYPE en_US.UTF-8

RUN apt-get update && apt-get install -y coreutils bash git wget make gettext python3 python3-pip python3-virtualenv curl

RUN curl https://dl.min.io/client/mc/release/linux-amd64/mc \
         --create-dirs \
         -o /usr/local/bin/mc
RUN chmod +x /usr/local/bin/mc

# RUN wget https://repo.anaconda.com/miniconda/Miniconda3-py37_22.11.1-1-Linux-x86_64.sh -O miniconda.sh && bash miniconda.sh -b -p /opt/conda
# RUN /opt/conda/bin/conda install -c conda-forge -y python==3.9

ADD . /opt/paper-downloader

RUN chmod +x /opt/paper-downloader/bin/launch.sh
RUN virtualenv -p python3 /opt/conda/envs/venv
RUN /opt/conda/envs/venv/bin/pip install /opt/paper-downloader

ENTRYPOINT ["/opt/paper-downloader/bin/launch.sh"]