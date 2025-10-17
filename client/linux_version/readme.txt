1️: Đặt file thực thi vào đúng vị trí

sudo mv lcit_monitor /usr/local/bin/
sudo chmod +x /usr/local/bin/lcit_monitor
   
2: Tạo file service cho systemd

sudo nano /etc/systemd/system/lcit_monitor.service
Thêm nội dung chuẩn (copy nguyên mẫu này):
[Unit]
Description=LCIT System Monitor Agent
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/lcit_monitor -start
ExecStop=/usr/local/bin/lcit_monitor -stop
ExecReload=/usr/local/bin/lcit_monitor -status
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target

3: Nạp lại daemon để nhận service mới

sudo systemctl daemon-reload
sudo systemctl start lcit_monitor.service
sudo systemctl status lcit_monitor.service

Nếu thấy Active: active (running) → OK ✅

4: Bật tự khởi động cùng hệ thống
sudo systemctl enable lcit_monitor.service