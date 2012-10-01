#!/bin/sh

##  /opt/mobile-init.sh
# This script reads /proc/cmdline for the location of the second stage script, downloads and execs that script
# It should be called from local.rc
# eg.
#
# sh /opt/mobile-init.sh &
#

## VARS
# kernel boot args path
KERNELCMD="/proc/cmdline"

# wget path
WGET="/usr/bin/wget"

# location to download second stage script
DL_PATH="/opt/scripts"

# default URL should be null
URL=''

## log function
# send arg to local syslog via logger
log () {
   logger -p local0.info -t "mobile-init.sh" "${1}"
   echo ${1} >> /opt/mobile.log
}

# Do some syslogging and exit
panic () {
   log ${1}
   exit 2
}

log "mobile-init.sh starting."

## sanity checks
# Check for kernel boot args
if ! [ -e ${KERNELCMD} ]
then
    panic "${KERNELCMD} not found!"
fi

# Check for wget
if ! [ -x ${WGET} ]
then
   panic "${WGET} not found!"
fi 


# read kernel boot args to var
CMDLINE=$(cat "${KERNELCMD}")

log "Reading boot args."

# loop though cmdline for vars
   for CMD_PARAM in ${CMDLINE}
   do
       case "${CMD_PARAM}" in
           mobile-imaging-url=*)
               URL="${CMD_PARAM#mobile-imaging-url=}"
               ;;
       esac
   done

# check for URL of second stage
if [ ${URL} ]
then
    log "second stage URL found."
else
    panic "mobile-imaging-url boot arg not found!"
fi 

# Prepare download location
rm -rf "${DL_PATH}"
mkdir -p "${DL_PATH}"

# Download main script
WGET_OUTPUT=$("${WGET}" "--output-document=${DL_PATH}/second-stage.sh" "${URL}" 2>&1)
if [ $? -ne 0 ]
then
   panic "wget failed: ${WGET_OUTPUT}"
else
   log "wget success: ${WGET_OUTPUT}"
fi

chmod 755 ${DL_PATH}/second-stage.sh

# exec mobile-init.sh
log "exec mobile-init.sh"
MOBILE_INIT_OUTPUT=$("${DL_PATH}/second-stage.sh" 2>&1)
if [ $? -ne 0 ]
then
    panic ${MOBILE_INIT_OUTPUT}
fi

exit 0
