#!/bin/sh

## VARS
KERNELCMD="/proc/cmdline"
WGET="/usr/bin/wget"
DL_PATH="/opt/scripts"
URL=''

# Do some syslogging and exit
panic () {
   echo "Panic!"
   exit 15
}

# sanity checks
if ! [ -e ${KERNELCMD} ]
then
    panic
fi

if ! [ -x ${WGET} ]
then
   panic
fi 

CMDLINE=$(cat "${KERNELCMD}")

# loop though cmdline for vars
   for CMD_PARAM in ${CMDLINE}
   do
       case "${CMD_PARAM}" in
           mobile-imaging-url=*)
               URL="${CMD_PARAM#mobile-imaging-url=}"
               ;;
       esac
   done

if ! [ ${URL} ]
then
    panic
fi 

# Prepare download location
rm -rf "${DL_PATH}"
mkdir -p "${DL_PATH}"

# Download main script
WGET_OUTPUT=$("${WGET}" "--output-document=${DL_PATH}/mobile-init.sh" "${URL}" 2>&1)
if [ $? -ne 0 ]
then
   echo ${WGET_OUTPUT}
   panic
fi

chmod 755 ${DL_PATH}/mobile-init.sh

# exec mobile-init.sh
MOBILE_INIT_OUTPUT=$("${DL_PATH}/mobile-init.sh" 2>&1)
if [ $? -ne 0 ]
then
    echo ${MOBILE_INIT_OUTPUT}
    panic
fi

exit 0
