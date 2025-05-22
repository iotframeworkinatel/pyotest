docker system prune -a

docker network create -d macvlan \
       --subnet=192.168.15.0/24 \
       --gateway=192.168.15.1 \
       -o parent=wlp2s0 \
       iot_macvlan

docker-compose up -d

sudo ip link add macvlan0 link wlp2s0 type macvlan mode bridge

sudo ip addr add 192.168.15.250/24 dev macvlan0

sudo ip link set macvlan0 up

sudo ip route add 192.168.15.30/32 dev macvlan0
sudo ip route add 192.168.15.31/32 dev macvlan0
sudo ip route add 192.168.15.32/32 dev macvlan0
sudo ip route add 192.168.15.33/32 dev macvlan0
sudo ip route add 192.168.15.34/32 dev macvlan0
sudo ip route add 192.168.15.35/32 dev macvlan0
sudo ip route add 192.168.15.36/32 dev macvlan0
sudo ip route add 192.168.15.37/32 dev macvlan0


# limpar configurações
sudo ip link rmv macvlan0
docker compose -f docker-compose-lucas.yml down