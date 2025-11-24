1) cd client
2) Command: dpkg-deb --build lcit_monitor_agent_deb
3) Deb file will be export in client folder
4) sudo HOSTNAME=<hostname> PLATFORM=<platfomr> dpkg -i lcit_monitor_agent_deb.deb
   vd: sudo HOSTNAME="Viettel Cloud" PLATFORM="Uddl lab" dpkg -i lcit_monitor_agent_deb.deb