# Simple APT Update

## Description

A GUI for basic tasks of package management using apt:

* Update the package cache
* Check for and list all available upgrades
* Download and install all available upgrades

## Dependencies

```shell
apt install python3-gi
```

## Installation

```shell
make
sudo make install
```

## Usage

The application requires root permissions:

```shell
sudo simple-apt-update
```

*Note:* The application registers `simple-apt-update.desktop`, using `pkexec`.
In GNOME, it will be available as an application called "Simple APT Update".

