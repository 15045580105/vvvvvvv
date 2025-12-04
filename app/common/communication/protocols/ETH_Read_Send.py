import threading
import time
import sys
import json
from scapy.all import sniff, sendp
from scapy.all import get_if_list, conf
from scapy.layers.l2 import Ether

from ETH_Protocol_Analysis import parse_ethernet_packet  # 导入分析模块
from app.common.communication.DataCenter.DataCenter import DataCenter  # 新增: 数据中心用于分发解析后的报文


class EthernetSniffer:
    def __init__(self, interface=None):
        """
        初始化以太网嗅探器

        Args:
            interface: 网络接口名称，如果为None则自动选择第一个可用接口
        """
        self.interface = interface
        self.sniffing = False
        self.sniffer_thread = None

        # 设置scapy使用npcap
        conf.use_pcap = True

        # 如果没有指定接口，则选择第一个可用接口
        if self.interface is None:
            interfaces = get_if_list()
            if interfaces:
                self.interface = interfaces[0]
                print(f"未指定接口，使用默认接口: {self.interface}")
            else:
                raise ValueError("未找到可用的网络接口")

    def packet_handler(self, packet):
        """处理接收到的数据包，使用ethAnalysis中的解析方法并分发给监听者.

        Args:
            packet: 接收到的数据包
        """
        # 获取原始字节数据
        raw_bytes = bytes(packet)

        # 先打印原始数据
        print("\n" + "=" * 60)
        print(f"原始数据 - 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print(f"原始字节数组: {raw_bytes.hex()}")

        # 打印十六进制转储（完整数据）
        print("十六进制转储:")
        for i in range(0, len(raw_bytes), 16):
            hex_str = " ".join(f"{b:02x}" for b in raw_bytes[i:i + 16])
            ascii_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in raw_bytes[i:i + 16])
            print(f"{i:04x}: {hex_str:<48} {ascii_str}")

        # 使用ethAnalysis中的解析方法
        result = parse_ethernet_packet(raw_bytes)

        # 按照ethAnalysis的格式打印结果
        print("\n" + "=" * 60)
        print(f"解析结果 - 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # 打印解析结果
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 新增: 将解析结果分发到 DataCenter, 供已注册监听者消费
        try:
            dc = DataCenter.get_instance()
            dc.on_parsed_packet(result, raw_bytes)
        except Exception as e:
            # 分发异常不影响嗅探本身, 仅打印提示
            print(f"[DataCenter] 分发解析报文时出错: {e}")

    def start(self):
        """开始嗅探数据包"""
        if self.sniffing:
            raise RuntimeError("嗅探器已经在运行")

        print(f"开始在接口 {self.interface} 上嗅探数据包...")
        print("按Ctrl+C停止嗅探")

        self.sniffing = True

        def sniff_thread():
            try:
                sniff(iface=self.interface, prn=self.packet_handler, store=0)
            except KeyboardInterrupt:
                print("\n嗅探已停止")
            except Exception as e:
                print(f"嗅探错误: {e}")
            finally:
                self.sniffing = False

        self.sniffer_thread = threading.Thread(target=sniff_thread)
        self.sniffer_thread.daemon = True
        self.sniffer_thread.start()

    def stop(self):
        """停止嗅探数据包"""
        if not self.sniffing:
            raise RuntimeError("嗅探器未运行")

        self.sniffing = False
        if self.sniffer_thread and self.sniffer_thread.is_alive():
            import signal
            import os
            os.kill(os.getpid(), signal.SIGINT)
            self.sniffer_thread.join(timeout=2)

    def is_running(self):
        """检查嗅探器是否正在运行"""
        return self.sniffing

    def send_ethernet_frame(self, dst_mac, src_mac=None, payload=None, ether_type=0x0800):
        """
        发送以太网数据帧

        Args:
            dst_mac: 目标MAC地址 (格式: "xx:xx:xx:xx:xx:xx")
            src_mac: 源MAC地址，如果为None则使用接口的MAC地址
            payload: 数据包负载，如果为None则使用默认负载
            ether_type: 以太网类型 (默认: 0x0800 - IPv4)

        Returns:
            bool: 发送是否成功
        """
        try:
            if src_mac is None:
                # 获取接口的MAC地址
                import subprocess
                result = subprocess.run(['getmac', '/fo', 'csv', '/nh'],
                                        capture_output=True, text=True)
                # 这里需要根据实际情况解析MAC地址
                # 简化处理，使用一个示例MAC
                src_mac = "00:11:22:33:44:55"

            if payload is None:
                payload = b"Hello from Npcap Python!"

            ethernet_frame = Ether(dst=dst_mac, src=src_mac, type=ether_type)
            packet = ethernet_frame / payload

            sendp(packet, iface=self.interface, verbose=False)
            return True
        except Exception as e:
            print(f"发送数据包错误: {e}")
            return False

    def send_someip_packet(self, dst_mac, src_mac=None,
                           service_id=0x1234, method_id=0x0001,
                           client_id=0x0001, session_id=0x0001,
                           protocol_version=0x01, interface_version=0x01,
                           message_type=0x00, return_code=0x00,
                           payload=None):
        """
        发送SOME/IP报文

        Args:
            dst_mac: 目标MAC地址
            src_mac: 源MAC地址
            service_id: 服务ID (16位)
            method_id: 方法ID (16位)
            client_id: 客户端ID (16位)
            session_id: 会话ID (16位)
            protocol_version: 协议版本 (8位)
            interface_version: 接口版本 (8位)
            message_type: 消息类型 (8位)
            return_code: 返回码 (8位)
            payload: SOME/IP负载数据

        Returns:
            bool: 发送是否成功
        """
        try:
            if src_mac is None:
                src_mac = "00:11:22:33:44:55"

            if payload is None:
                payload = b"SOME/IP Test Payload"

            # 构建SOME/IP头部 (16字节)
            someip_header = (
                    bytes([(service_id >> 8) & 0xFF, service_id & 0xFF]) +  # Service ID
                    bytes([(method_id >> 8) & 0xFF, method_id & 0xFF]) +  # Method ID
                    bytes([0x00, 0x00, 0x00, 0x00]) +  # Length (稍后填充)
                    bytes([client_id >> 8, client_id & 0xFF]) +  # Client ID
                    bytes([session_id >> 8, session_id & 0xFF]) +  # Session ID
                    bytes([protocol_version]) +  # Protocol Version
                    bytes([interface_version]) +  # Interface Version
                    bytes([message_type]) +  # Message Type
                    bytes([return_code])  # Return Code
            )

            # 计算总长度并更新长度字段
            total_length = len(someip_header) - 8 + len(payload)  # 减去前8字节
            someip_header = (someip_header[:4] +
                             bytes([(total_length >> 24) & 0xFF,
                                    (total_length >> 16) & 0xFF,
                                    (total_length >> 8) & 0xFF,
                                    total_length & 0xFF]) +
                             someip_header[8:])

            # 构建完整SOME/IP报文
            someip_packet = someip_header + payload

            # 发送以太网帧，使用SOME/IP的以太网类型 0x80B5
            return self.send_ethernet_frame(dst_mac, src_mac, someip_packet, 0x80B5)

        except Exception as e:
            print(f"发送SOME/IP报文错误: {e}")
            return False

    def send_doip_packet(self, dst_mac, src_mac=None,
                         payload_type=0x8001, payload=None):
        """
        发送DOIP报文

        Args:
            dst_mac: 目标MAC地址
            src_mac: 源MAC地址
            payload_type: 负载类型 (16位)
            payload: DOIP负载数据

        Returns:
            bool: 发送是否成功
        """
        try:
            if src_mac is None:
                src_mac = "00:11:22:33:44:55"

            if payload is None:
                # 默认DOIP负载：车辆识别请求
                payload = b"\x00\x00\x00\x00\x00\x00\x00\x00"  # 8字节零填充

            # 构建DOIP头部 (8字节)
            doip_header = (
                    bytes([0x02]) +  # DOIP协议版本
                    bytes([0xFD]) +  # 反向协议版本
                    bytes([(payload_type >> 8) & 0xFF,  # Payload Type
                           payload_type & 0xFF]) +
                    bytes([(len(payload) >> 24) & 0xFF,  # Payload Length
                           (len(payload) >> 16) & 0xFF,
                           (len(payload) >> 8) & 0xFF,
                           len(payload) & 0xFF])
            )

            # 构建完整DOIP报文
            doip_packet = doip_header + payload

            # 发送以太网帧，使用DOIP的以太网类型 0x80F9
            return self.send_ethernet_frame(dst_mac, src_mac, doip_packet, 0x80F9)

        except Exception as e:
            print(f"发送DOIP报文错误: {e}")
            return False

    def send_doip_vehicle_identification_request(self, dst_mac, src_mac=None):
        """
        发送DOIP车辆识别请求

        Args:
            dst_mac: 目标MAC地址
            src_mac: 源MAC地址

        Returns:
            bool: 发送是否成功
        """
        # 车辆识别请求的负载类型为0x0004，负载为空
        return self.send_doip_packet(dst_mac, src_mac, 0x0004, b"")

    def send_doip_routing_activation_request(self, dst_mac, src_mac=None,
                                             source_address=0x0E00, activation_type=0x00):
        """
        发送DOIP路由激活请求

        Args:
            dst_mac: 目标MAC地址
            src_mac: 源MAC地址
            source_address: 源地址 (16位)
            activation_type: 激活类型 (8位)

        Returns:
            bool: 发送是否成功
        """
        payload = (
                bytes([(source_address >> 8) & 0xFF, source_address & 0xFF]) +
                bytes([activation_type]) +
                bytes([0x00, 0x00, 0x00, 0x00, 0x00])  # 保留字段
        )
        return self.send_doip_packet(dst_mac, src_mac, 0x0005, payload)

    def send_someip_rpc_request(self, dst_mac, src_mac=None,
                                service_id=0x1234, method_id=0x0001,
                                client_id=0x0001, session_id=0x0001,
                                rpc_payload=None):
        """
        发送SOME/IP RPC请求

        Args:
            dst_mac: 目标MAC地址
            src_mac: 源MAC地址
            service_id: 服务ID
            method_id: 方法ID
            client_id: 客户端ID
            session_id: 会话ID
            rpc_payload: RPC负载数据

        Returns:
            bool: 发送是否成功
        """
        if rpc_payload is None:
            rpc_payload = b"\x00\x01\x02\x03\x04\x05"  # 示例RPC负载

        return self.send_someip_packet(
            dst_mac, src_mac,
            service_id=service_id,
            method_id=method_id,
            client_id=client_id,
            session_id=session_id,
            message_type=0x00,  # REQUEST
            return_code=0x00,  # E_OK
            payload=rpc_payload
        )

    def send_someip_notification(self, dst_mac, src_mac=None,
                                 service_id=0x1234, method_id=0x8001,
                                 client_id=0x0001, session_id=0x0001,
                                 notification_data=None):
        """
        发送SOME/IP通知

        Args:
            dst_mac: 目标MAC地址
            src_mac: 源MAC地址
            service_id: 服务ID
            method_id: 方法ID (事件ID，最高位为1)
            client_id: 客户端ID
            session_id: 会话ID
            notification_data: 通知数据

        Returns:
            bool: 发送是否成功
        """
        if notification_data is None:
            notification_data = b"\x01\x02\x03\x04"  # 示例通知数据

        return self.send_someip_packet(
            dst_mac, src_mac,
            service_id=service_id,
            method_id=method_id,
            client_id=client_id,
            session_id=session_id,
            message_type=0x02,  # NOTIFICATION
            return_code=0x00,  # E_OK
            payload=notification_data
        )

    def send_raw_packet(self, packet):
        """
        发送原始数据包

        Args:
            packet: 要发送的Scapy数据包对象

        Returns:
            bool: 发送是否成功
        """
        try:
            sendp(packet, iface=self.interface, verbose=False)
            return True
        except Exception as e:
            print(f"发送数据包错误: {e}")
            return False


def main():
    """主函数"""
    try:
        # 创建以太网嗅探器实例
        sniffer = EthernetSniffer()

        # 显示可用接口
        print("可用网络接口:")
        for i, iface in enumerate(get_if_list()):
            print(f"  {i + 1}. {iface}")

        # 选择接口
        try:
            iface_choice = input(f"选择接口 (1-{len(get_if_list())}, 回车使用默认): ").strip()
            if iface_choice:
                iface_index = int(iface_choice) - 1
                if 0 <= iface_index < len(get_if_list()):
                    sniffer.interface = get_if_list()[iface_index]
        except (ValueError, IndexError):
            print("无效选择，使用默认接口")

        print(f"使用接口: {sniffer.interface}")

        # 启动嗅探
        sniffer.start()

        # 主循环
        while True:
            print("\n" + "=" * 50)
            print("1. 发送以太网数据包")
            print("2. 发送SOME/IP报文")
            print("3. 发送DOIP报文")
            print("4. 发送预定义测试报文")
            print("5. 检查嗅探状态")
            print("6. 停止嗅探")
            print("7. 退出")
            print("=" * 50)

            choice = input("请选择操作: ").strip()

            if choice == "1":
                dst_mac = input("输入目标MAC地址 (格式: xx:xx:xx:xx:xx:xx): ").strip()
                src_mac = input("输入源MAC地址 (回车使用默认): ").strip() or None
                payload = input("输入负载数据 (回车使用默认): ").strip()
                payload = payload.encode() if payload else None

                try:
                    ether_type = input("输入以太网类型 (十六进制, 回车使用0x0800): ").strip()
                    ether_type = int(ether_type, 16) if ether_type else 0x0800
                except ValueError:
                    print("无效的以太网类型，使用默认值0x0800")
                    ether_type = 0x0800

                if sniffer.send_ethernet_frame(dst_mac, src_mac, payload, ether_type):
                    print("数据包发送成功")
                else:
                    print("数据包发送失败")

            elif choice == "2":
                dst_mac = input("输入目标MAC地址: ").strip()
                src_mac = input("输入源MAC地址 (回车使用默认): ").strip() or None

                try:
                    service_id = int(input("输入服务ID (十六进制, 回车使用0x1234): ").strip() or "1234", 16)
                    method_id = int(input("输入方法ID (十六进制, 回车使用0x0001): ").strip() or "0001", 16)
                    client_id = int(input("输入客户端ID (十六进制, 回车使用0x0001): ").strip() or "0001", 16)
                    session_id = int(input("输入会话ID (十六进制, 回车使用0x0001): ").strip() or "0001", 16)

                    payload_hex = input("输入负载数据 (十六进制, 回车使用默认): ").strip()
                    payload = bytes.fromhex(payload_hex) if payload_hex else None

                    if sniffer.send_someip_packet(dst_mac, src_mac, service_id, method_id,
                                                  client_id, session_id, payload=payload):
                        print("SOME/IP报文发送成功")
                    else:
                        print("SOME/IP报文发送失败")
                except ValueError as e:
                    print(f"输入格式错误: {e}")

            elif choice == "3":
                dst_mac = input("输入目标MAC地址: ").strip()
                src_mac = input("输入源MAC地址 (回车使用默认): ").strip() or None

                print("选择DOIP报文类型:")
                print("1. 车辆识别请求")
                print("2. 路由激活请求")
                print("3. 自定义DOIP报文")

                doip_choice = input("请选择: ").strip()

                if doip_choice == "1":
                    if sniffer.send_doip_vehicle_identification_request(dst_mac, src_mac):
                        print("DOIP车辆识别请求发送成功")
                    else:
                        print("DOIP车辆识别请求发送失败")

                elif doip_choice == "2":
                    try:
                        source_addr = int(input("输入源地址 (十六进制, 回车使用0x0E00): ").strip() or "0E00", 16)
                        if sniffer.send_doip_routing_activation_request(dst_mac, src_mac, source_addr):
                            print("DOIP路由激活请求发送成功")
                        else:
                            print("DOIP路由激活请求发送失败")
                    except ValueError as e:
                        print(f"输入格式错误: {e}")

                elif doip_choice == "3":
                    try:
                        payload_type = int(input("输入负载类型 (十六进制, 回车使用0x8001): ").strip() or "8001", 16)
                        payload_hex = input("输入负载数据 (十六进制, 回车使用默认): ").strip()
                        payload = bytes.fromhex(payload_hex) if payload_hex else None

                        if sniffer.send_doip_packet(dst_mac, src_mac, payload_type, payload):
                            print("自定义DOIP报文发送成功")
                        else:
                            print("自定义DOIP报文发送失败")
                    except ValueError as e:
                        print(f"输入格式错误: {e}")
                else:
                    print("无效选择")

            elif choice == "4":
                dst_mac = input("输入目标MAC地址: ").strip()
                src_mac = input("输入源MAC地址 (回车使用默认): ").strip() or None

                print("选择预定义测试报文:")
                print("1. SOME/IP RPC请求")
                print("2. SOME/IP 事件通知")

                test_choice = input("请选择: ").strip()

                if test_choice == "1":
                    if sniffer.send_someip_rpc_request(dst_mac, src_mac):
                        print("SOME/IP RPC请求发送成功")
                    else:
                        print("SOME/IP RPC请求发送失败")

                elif test_choice == "2":
                    if sniffer.send_someip_notification(dst_mac, src_mac):
                        print("SOME/IP事件通知发送成功")
                    else:
                        print("SOME/IP事件通知发送失败")
                else:
                    print("无效选择")

            elif choice == "5":
                print(f"嗅探状态: {'运行中' if sniffer.is_running() else '已停止'}")

            elif choice == "6":
                if sniffer.is_running():
                    sniffer.stop()
                    print("嗅探已停止")
                else:
                    print("嗅探器未运行")

            elif choice == "7":
                if sniffer.is_running():
                    sniffer.stop()
                print("退出程序...")
                break
            else:
                print("无效选择，请重新输入")

    except KeyboardInterrupt:
        print("\n收到中断信号，退出程序...")
    except Exception as e:
        print(f"程序错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        import scapy.all as scapy
    except ImportError:
        print("错误: 未找到scapy库，请先安装: pip install scapy")
        sys.exit(1)

    main()