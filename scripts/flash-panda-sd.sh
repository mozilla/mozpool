#!/bin/bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Flashes a rel-eng-style build, consisting of tarball artifacts from a B2G
# or Android build, to an attached disk.

DEFAULT_TREE=cedar-panda
DEFAULT_BUILD_IDX_URL=https://pvtbuilds.mozilla.org/pub/mozilla.org/b2g/tinderbox-builds/${DEFAULT_TREE}/
DEFAULT_PRESEED_IDX_URL=http://puppetagain.pub.build.mozilla.org/data/bmm/preseed/

function usage
{
    echo "$0 [-b <build path/URL>] [-p <preseed URL>] [-u] <device>"
    echo
    echo "If given, build path/URL should be to the directory containing the"
    echo "build artifacts (system.tar.bz2, boot.tar.bz2, userdata.tar.bz2)"
    echo "If not given, fetches latest from ${DEFAULT_TREE}."
    echo
    echo "If given, preseed path/URL should point to a compressed preseed"
    echo "image."
    echo "If not given, fetches latest image."
    echo
    echo "If -u is given, prompts for pvtbuilds username and password and"
    echo "creates a temporary wgetrc file to avoid putting the password in the"
    echo "process list."
    echo "If not given, uses the default wgetrc file for permissions."
    echo
    echo "Several steps of this script require root access and may produce"
    echo "sudo prompts.  To avoid repeated prompts, run this whole script with"
    echo "sudo."
}

while getopts hb:p:u OPT
do
    case "$OPT" in
        h)
            usage
            exit 0
            ;;
        b)
            BUILD_ARG=$OPTARG
            ;;
        p)
            PRESEED_ARG=$OPTARG
            ;;
        u)
            USER_PROMPT=1
            ;;
        \?)
            # getopts issues an error message
            usage
            exit 1
            ;;
    esac
done

shift `expr $OPTIND - 1`

DEVICE=$1

if [ ! "${DEVICE}" ]
then
    usage
    exit 1
fi

if [ ! -b ${DEVICE} ]
then
    echo "${DEVICE} is not a block device."
    exit 1
fi

function get_build_path
{
    if [ ! "${BUILD_ARG}" ]
    then
        echo "No build path/URL given; checking for latest ${DEFAULT_TREE} build"
        BUILD_ID=$(wget -nv -O - ${DEFAULT_BUILD_IDX_URL} | grep -E -o 'a href="[[:digit:]]{14}/"' | uniq | sort | tail -n -1 | cut -d \" -f 2 | cut -d / -f 1)
        if [ ! "${BUILD_ID}" ]
        then
            echo "Could not find build at ${DEFAULT_BUILD_IDX_URL}."
            exit 1
        fi
        BUILD_ARG=${DEFAULT_BUILD_IDX_URL}${BUILD_ID}
        echo "Using ${DEFAULT_TREE} build ${BUILD_ID}."
    fi

    echo "${BUILD_ARG}" | grep -E "^[[:alnum:]]+://"
    if [ "$?" == "0" ]
    then
        BUILD_DIR=${TMPDIR}/artifacts/
        echo "Fetching build artifacts from ${BUILD_ARG}"
        echo
        wget -nv --directory-prefix=${BUILD_DIR} ${BUILD_ARG}/system.tar.bz2
        wget -nv --directory-prefix=${BUILD_DIR} ${BUILD_ARG}/userdata.tar.bz2
        wget -nv --directory-prefix=${BUILD_DIR} ${BUILD_ARG}/boot.tar.bz2
    else
        BUILD_DIR=${BUILD_ARG}
    fi
}


function get_preseed_path
{
    if [ ! "${PRESEED_ARG}" ]
    then
        echo "No preseed path/URL given; checking for latest"
        PRESEED_ZIP_NAME=$(wget -nv -O - ${DEFAULT_PRESEED_IDX_URL} | grep -E -o "uboot-preseed.[[:digit:]]+.img.bz2" | uniq | sort | tail -n -1)
        PRESEED_ARG=${DEFAULT_PRESEED_IDX_URL}${PRESEED_ZIP_NAME}
    else
        PRESEED_ZIP_NAME=$(basename "${PRESEED_ARG}")
    fi

    PRESEED_DIR=${TMPDIR}/preseed/
    PRESEED_NAME=$(echo "${PRESEED_ZIP_NAME}" | sed -e 's/.bz2$//')

    echo "${PRESEED_ARG}" | grep -E "^[[:alnum:]]+://"
    if [ "$?" == "0" ]
    then
        echo "Fetching preseed image ${PRESEED_ARG}"
        wget -nv --directory-prefix=${PRESEED_DIR} ${PRESEED_ARG}
    else
        # Copy image archive since we decompress it in place.
        echo "Copying preseed image"
        cp ${PRESEED_ARG} ${PRESEED_DIR}/${PRESEED_ZIP_NAME}
        if [ "$?" != "0" ]
        then
            exit $?
        fi
    fi
}


TMPDIR=$(mktemp -d)
trap "echo 'Cleaning up'; rm -rf ${TMPDIR}" EXIT

mkdir -p ${TMPDIR}/preseed ${TMPDIR}/artifacts ${TMPDIR}/mnt/boot ${TMPDIR}/mnt/system ${TMPDIR}/mnt/userdata

if [ "${USER_PROMPT}" ]
then
    WGETRC=${TMPDIR}/wgetrc
    read -p "Username for pvtbuilds.mozilla.org: " USERNAME
    read -s -p "Password for pvtbuilds.mozilla.org: " PASSWORD
    echo
    echo -e "user=${USERNAME}\npassword=${PASSWORD}" > ${WGETRC}
    unset USERNAME
    unset PASSWORD
    export WGETRC
fi

get_build_path
get_preseed_path

if [ ! -e ${PRESEED_DIR}/${PRESEED_ZIP_NAME} ]
then
    echo "Preseed image not found."
    exit 1
fi

if [ ! -e ${BUILD_DIR}/system.tar.bz2 -o ! -e ${BUILD_DIR}/userdata.tar.bz2 -o ! -e ${BUILD_DIR}/boot.tar.bz2 ]
then
    echo "Not all artifacts found."
    exit 1
fi

echo "Decompressing preseed and writing to ${DEVICE} (requires root)"
bzip2 -dc ${PRESEED_DIR}/${PRESEED_ZIP_NAME} | sudo dd of=${DEVICE} bs=1M

echo "Rereading partition table (requires root)"
sudo partprobe ${DEVICE}

echo "Formatting partitions"
mkfs.ext4 -L "System" ${DEVICE}2
mkfs.ext4 -L "Cache" ${DEVICE}3
mkfs.ext4 -L "Userdata" ${DEVICE}5
mkfs.ext4 -L "Media" ${DEVICE}6

echo "Mounting partitions (requires root)"
sudo mount -t vfat -o uid=$(id -u),gid=$(id -g) ${DEVICE}1 ${TMPDIR}/mnt/boot
sudo mount -t ext4 ${DEVICE}2 ${TMPDIR}/mnt/system
sudo mount -t ext4 ${DEVICE}5 ${TMPDIR}/mnt/userdata

echo "Extracting artifacts"
tar -jxf ${BUILD_DIR}/boot.tar.bz2 -C ${TMPDIR} boot/kernel boot/ramdisk.img
tar -jxf ${BUILD_DIR}/system.tar.bz2 -C ${TMPDIR}/mnt/system --strip=1 system
tar -jxf ${BUILD_DIR}/userdata.tar.bz2 -C ${TMPDIR}/mnt/userdata --strip=1 data

echo "Making boot images"
mkimage -A arm -T kernel -O linux -C none -n "B2G Kernel $(whoami) $(date +'%Y%m%d'00)" -a 0x80008000 -e 0x80008000 -d ${TMPDIR}/boot/kernel ${TMPDIR}/mnt/boot/uImage
mkimage -A arm -T ramdisk -O linux -C none -n "B2G Initrd $(whoami) $(date +'%Y%m%d'00)" -a 0x00000000 -e 0x00000000 -d ${TMPDIR}/boot/ramdisk.img ${TMPDIR}/mnt/boot/uInitrd

grep -q "^run bootpxefirst$" ${TMPDIR}/mnt/boot/boot.txt
if [ "$?" == "0" ]
then
    echo "Disabling pxeboot"
    cat ${TMPDIR}/mnt/boot/boot.txt | sed 's/^run bootpxefirst$/run bootandroid/' > ${TMPDIR}/boot.txt
    mv ${TMPDIR}/boot.txt ${TMPDIR}/mnt/boot/boot.txt
    mkimage -A arm -T script -O linux -C none -a 0 -e 0 -n "boot.scr" -d ${TMPDIR}/mnt/boot/boot.txt ${TMPDIR}/mnt/boot/boot.scr
fi

echo "Unmounting partitions (requires root)"
sudo umount ${TMPDIR}/mnt/boot ${TMPDIR}/mnt/system ${TMPDIR}/mnt/userdata

exit 0
