sudo docker run --detach --restart unless-stopped -v /var/litter-robot-intercept:/litter-robot/ -p 2000:2000/udp -p 2001:2001/udp --user 1000 litter_robot_intercept
