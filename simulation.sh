docker system prune -a

docker network create -d macvlan \
       --subnet=192.168.2.0/24 \
       --gateway=192.168.2.1 \
       -o parent=enp4s0 \
       iot_macvlan

docker-compose up -d

sudo ip link add macvlan0 link enp4s0 type macvlan mode bridge

sudo ip addr add 192.168.2.250/24 dev macvlan0

sudo ip link set macvlan0 up

sudo ip route add 192.168.2.30/32 dev macvlan0
sudo ip route add 192.168.2.31/32 dev macvlan0
sudo ip route add 192.168.2.32/32 dev macvlan0 