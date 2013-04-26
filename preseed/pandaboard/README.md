Panda Board Preseed Components
==============================

This directory contains the file components that make up the preseed image.  This includes the essential boot loader files and a partition table structure.

File list and descriptions
--------------------------

boot.txt
: U-boot script source file

boot.scr
: Boot script encapsulated with u-boot header

MLO
: First stage boot loader

u-boot.img
: Second stage boot loader

omap4-panda.dtb
: Omap4 kernel device tree file

mmc_part_table
: SD Card partition table structure.  Use sfdisk to write recreate partition table eg. sfdisk /dev/mmcblk0 < mmc_part_table.img --force 

VERSION
: Version string in the format YYYYMMDDNN.  This file should be updated when any file in this directory is changed.

Sources
-------

U-boot is covered under the GPLv2. The Linaro source tree can be found at [http://git.linaro.org/git-ro/boot/u-boot-linaro-stable.git]

