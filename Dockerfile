FROM ubuntu:16.04

RUN apt-get update; apt-get install -y software-properties-common

# https://wiki.ubuntu.com/ServerTeam/CloudArchive
RUN add-apt-repository -y cloud-archive:ocata

RUN apt-get update; apt-get install -y \
    nano \
    rsyslog \
    supervisor \
    memcached \
    swift \
    swift-proxy \
    swift-object \
    swift-account \
    swift-container \
    swift-object

# dependencies for swift3
RUN apt-get install -y \
    git \
    python-dev \
    python-pip \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev

RUN pip install lxml

# requests version with ubuntu 14.04 not comptabible with Swift3, upgrade
RUN pip install requests --upgrade

# a couple of additional Python packages
RUN pip install exifread
RUN pip install Pillow

# for keystone auth, we need the keystone middleware
RUN pip install keystonemiddleware

# client lib to talk to the elasticsearch server
RUN pip install elasticsearch-dsl

# to get a decently recent version of swift3, you have to git clone...
RUN cd /root; git clone https://github.com/stackforge/swift3.git
RUN cd /root/swift3; python setup.py install

#RUN pip install python_swiftclient

COPY files/dispersion.conf /etc/swift/dispersion.conf
COPY files/rsyncd.conf /etc/rsyncd.conf
COPY files/account-server.conf /etc/swift/account-server.conf
COPY files/object-server.conf /etc/swift/object-server.conf
COPY files/container-server.conf /etc/swift/container-server.conf
COPY files/proxy-server-keystone.conf /etc/swift/proxy-server.conf
COPY files/swift.conf /etc/swift/swift.conf
COPY files/startmain.sh /usr/local/bin/startmain.sh
COPY files/container-reconciler.conf /etc/swift/container-reconciler.conf
COPY files/middleware/exif2metadata.py /usr/lib/python2.7/dist-packages/swift/common/middleware/exif2metadata.py
COPY files/middleware/generate_thumb.py /usr/lib/python2.7/dist-packages/swift/common/middleware/generate_thumb.py
COPY files/middleware/index_elastic.py /usr/lib/python2.7/dist-packages/swift/common/middleware/index_elastic.py
COPY files/middleware/search_elastic.py /usr/lib/python2.7/dist-packages/swift/common/middleware/search_elastic.py

EXPOSE 8080
CMD ["bash", "/usr/local/bin/startmain.sh"]
