# SOME/IP 多客户端 / 多服务双向测试

## 测试目标

`app/common/communication/clients/someip.py` 可以同时验证两类链路：

1. **VCC Client → 设备 Service**：发送 FindService，然后调用 RPC Method 或订阅 Event。
2. **设备 Client → VCC Service**：VCC 响应 FindService，并监听设备发来的 RPC Request。

SOME/IP UDP 本身没有 TCP 意义上的“连接”。本工具将以下结果作为可通信依据：

- Client 方向收到合法 Response/Notification；
- Service 方向收到设备 Request 并成功返回 Response。

仅 `start()` 成功代表本地端口绑定成功，不代表设备链路成功。

## 配置

复制根目录下的 `someip_device_test.example.json`，例如：

```powershell
Copy-Item .\someip_device_test.example.json .\someip_device_test.json
```

根据设备 SOME/IP 接口矩阵修改：

- `network.local_ip`：VCC 所在网卡 IPv4 地址；
- `network.device_ip`：设备单播 IPv4 地址；
- `network.multicast_ip` / `sd_port`：双方约定的 SOME/IP-SD 地址；
- `clients`：VCC 需要创建的 Client ID 和本地端口；
- `remote_services`：设备提供、VCC 要调用的 Service；
- `provided_services`：VCC 提供、设备 Client 会调用的 Service；
- `request_payload_hex`：VCC 请求 Payload；
- `expected_response_hex`：已知响应时填写；为 `null` 时只检查是否收到响应；
- `response_payload_hex`：VCC Service 返回给设备的 Payload；
- `expected_requests`：观察窗口内设备至少应调用本 Service 的次数；
- `duration`：完成正向测试后，继续等待设备反向调用的秒数。

ID 可写十进制或字符串形式的十六进制，如 `"0x1055"`。

## 运行

在项目根目录执行双向真实设备测试：

```powershell
python -m app.common.communication.clients.someip --config .\someip_device_test.json --role device --debug
```

只测试 VCC Client 调用设备 Service：

```powershell
python -m app.common.communication.clients.someip --config .\someip_device_test.json --role client
```

只启动 VCC Service，等待设备 Client 调用：

```powershell
python -m app.common.communication.clients.someip --config .\someip_device_test.json --role service
```

运行不依赖设备的本机回归：

```powershell
python -m app.common.communication.clients.someip --role all --clients 3 --services 2
```

## 结果说明

- `[PASS] Client -> Service`：收到设备 Response/Notification，且配置了期望 Payload 时内容一致；
- `[PASS] 设备 Client -> 本地 Service`：收到请求次数不少于 `expected_requests`；
- 进程退出码 `0`：所有要求通过；退出码 `1`：至少一条链路失败；退出码 `2`：配置错误。

## Windows VLAN 注意事项

- 推荐在网卡驱动/设备管理器中配置 VLAN 虚拟接口，并将 `vlan_id` 设为 `null`，让系统 socket 正常处理收发。
- `SomeIPClient` 的手工 Scapy VLAN 模式可用于 Client UDP 发包，但测试 Provider 使用系统 UDP socket，不能自行添加 802.1Q Tag。
- 使用手工 VLAN 时需安装 Npcap，并设置正确的 `client_mac` / `target_mac`。
- 测试前确认 Windows 防火墙允许 Python 访问 SD 端口及所有业务 UDP 端口。

