from udsoncan import Response
import udsoncan


class UDSParser:
    def __init__(self):
        self.service_names = {
            0x10: "DiagnosticSessionControl",
            0x11: "ECUReset",
            0x22: "ReadDataByIdentifier",
            0x23: "ReadMemoryByAddress",
            0x27: "SecurityAccess",
            0x28: "CommunicationControl",
            0x2E: "WriteDataByIdentifier",
            0x2F: "InputOutputControlByIdentifier",
            0x3E: "TesterPresent",
            0x85: "DTCControl",
            0x19: "ReadDTCInformation",
            0x14: "ClearDiagnosticInformation",
            0x34: "RequestDownload",
            0x35: "RequestUpload",
            0x36: "TransferData",
            0x37: "RequestTransferExit"
        }

    def parse_uds_message(self, uds_payload, is_response=True):
        """解析UDS消息"""
        if not uds_payload:
            return {"error": "空载荷"}

        try:
            result = {
                "raw_data": uds_payload.hex().upper(),
                "length": len(uds_payload)
            }

            # 检查是否是负响应
            if uds_payload[0] == 0x7F and len(uds_payload) >= 3:
                return self._parse_negative_response(uds_payload)

            service_id = uds_payload[0]
            result["service_id"] = f"0x{service_id:02X}"
            result["service_name"] = self.service_names.get(service_id, "Unknown")
            result["is_response"] = is_response

            # 如果是响应，服务ID = 请求ID + 0x40
            if is_response and service_id > 0x40:
                request_service = service_id - 0x40
                result["corresponding_request"] = f"0x{request_service:02X}"

            # 根据具体服务进行详细解析
            if service_id == 0x22:  # ReadDataByIdentifier
                self._parse_read_data_by_identifier(uds_payload, result)
            elif service_id == 0x2E:  # WriteDataByIdentifier
                self._parse_write_data_by_identifier(uds_payload, result)
            elif service_id == 0x10:  # DiagnosticSessionControl
                self._parse_diagnostic_session_control(uds_payload, result)
            # 可以继续添加其他服务的解析方法...

            return result

        except Exception as e:
            return {"error": f"解析失败: {str(e)}", "raw_data": uds_payload.hex().upper()}

    def _parse_negative_response(self, uds_payload):
        """解析负响应"""
        return {
            "type": "NegativeResponse",
            "request_service": f"0x{uds_payload[1]:02X}",
            "response_code": f"0x{uds_payload[2]:02X}",
            "response_name": self._get_negative_response_name(uds_payload[2]),
            "raw_data": uds_payload.hex().upper()
        }

    def _parse_read_data_by_identifier(self, uds_payload, result):
        """解析读数据标识符"""
        if len(uds_payload) >= 3:
            data_identifier = int.from_bytes(uds_payload[1:3], 'big')
            result["data_identifier"] = f"0x{data_identifier:04X}"
            if len(uds_payload) > 3:
                result["data"] = uds_payload[3:].hex().upper()

    def _parse_write_data_by_identifier(self, uds_payload, result):
        """解析写数据标识符"""
        if len(uds_payload) >= 3:
            data_identifier = int.from_bytes(uds_payload[1:3], 'big')
            result["data_identifier"] = f"0x{data_identifier:04X}"
            if len(uds_payload) > 3:
                result["data_to_write"] = uds_payload[3:].hex().upper()

    def _parse_diagnostic_session_control(self, uds_payload, result):
        """解析诊断会话控制"""
        if len(uds_payload) >= 2:
            session_type = uds_payload[1]
            result["session_type"] = f"0x{session_type:02X}"
            session_names = {
                0x01: "DefaultSession",
                0x02: "ProgrammingSession",
                0x03: "ExtendedDiagnosticSession"
            }
            result["session_name"] = session_names.get(session_type, "Unknown")

    def _get_negative_response_name(self, code):
        """获取负响应码名称"""
        nrc_names = {
            0x11: "serviceNotSupported",
            0x12: "subFunctionNotSupported",
            0x13: "incorrectMessageLengthOrInvalidFormat",
            0x22: "conditionsNotCorrect",
            0x31: "requestOutOfRange",
            0x33: "securityAccessDenied",
            0x35: "invalidKey",
            0x36: "exceedNumberOfAttempts",
            0x37: "requiredTimeDelayNotExpired",
            0x78: "requestCorrectlyReceived-ResponsePending"
        }
        return nrc_names.get(code, "unknownError")


# 使用示例
parser = UDSParser()

# 测试不同的UDS消息
test_messages = [
    b'\x62\xF1\x90\x4C\x53\x56\x4E\x56\x31\x32\x33\x34\x35\x36\x37\x38\x39\x30\x31\x32',  # 正响应
    b'\x7F\x22\x31',  # 负响应
    b'\x50\x01',  # 诊断会话控制响应
    b'\x6E\xF1\x90\x12\x34\x56',  # 写数据标识符响应
]
if __name__ == "__main__":
    for i, msg in enumerate(test_messages):
        print(f"\n--- 消息 {i + 1} 解析结果 ---")
        result = parser.parse_uds_message(msg)
        for key, value in result.items():
            print(f"{key}: {value}")