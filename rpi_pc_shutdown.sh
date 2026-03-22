#!/bin/bash
#set
GPIOpinOut=14
GPIOpinIn=15

#set output pin with status high
pinctrl set $GPIOpinOut op pn dh
 
#set input pin
pinctrl set $GPIOpinIn ip
 
#wait for shutdown signal
while true
do
  sleep 1
  signal=$(pinctrl get $GPIOpinIn | cut -d " " -f8 )
  if [ "$signal" != "hi" ]
  then
    echo "Shutdown Raspberry"
    shutdown -h now
    pinctrl set $GPIOpinOut dl
    exit 0
  fi
done
