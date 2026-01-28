def extract_routine_data(raw_data, routine_control_type_val=None):
    """
    从给定的row_data中提取'01:startRoutine'对应的值
    
    Args:
        raw_data: 包含modes字典的数据结构
        
    Returns:
        dict: 包含'01:startRoutine'对应的数据，如果找不到则返回None
    """
    # 检查是否有modes字段
    if 'modes' not in raw_data:
        return None
    
    modes = raw_data['modes']
    
    # 检查routine_control_type_val是否在modes中
    # routine_control_type_val = '01:startRoutine'
    if routine_control_type_val in modes:
        return modes[routine_control_type_val]
    
    return None


def get_specific_arrays(raw_data, routine_control_type_val='01:startRoutine'):
    """
    获取指定routine类型下的Request和Response数组
    
    Args:
        raw_data: 包含完整数据的字典
        routine_control_type_val: 要查找的routine控制类型，默认为'01:startRoutine'
        
    Returns:
        tuple: (request_array, response_array) 或 (None, None) 如果未找到
    """
    routine_data = extract_routine_data(raw_data, '01:startRoutine')
    
    if routine_data is None:
        return None, None
    
    # 提取请求和响应数组
    request_array = routine_data.get('RoutineControlOption(Request)', [])
    response_array = routine_data.get('routineStatus(Reponse)', [])  # 注意原数据中是Reponse而非Response
    
    return request_array, response_array


if __name__ == "__main__":
    # 测试数据（来自用户提供的数据）
    raw_data = {
        'description_c': 'ETH 总线通道镜像开关',
        'description_e': 'CCU_ETHBUSMirrorSwitch',
        'did_number': '0xBEE7',
        'modes': {
            '01:startRoutine': {
                'RoutineControlOption(Request)': [
                    {
                        'bit': '0',
                        'byte': '#5',
                        'conversion_c': '0=禁止\n1=使能',
                        'conversion_e': '0=Disable\n1=Enable',
                        'encoding': 'enum',
                        'sub_data_name_c': '使能Port 0~Port 10 + Port 12 + Port 13到OBD Port',
                        'sub_data_name_e': 'Switch_Mirror0'
                    },
                    {
                        'bit': '1',
                        'byte': '#5',
                        'conversion_c': '0=禁止\n1=使能',
                        'conversion_e': '0=Disable\n1=Enable',
                        'encoding': 'enum',
                        'sub_data_name_c': '使能Port 11到OBD Port',
                        'sub_data_name_e': 'Switch_Mirror1'
                    },
                    {
                        'bit': '2',
                        'byte': '#5',
                        'conversion_c': '0=禁止\n1=使能',
                        'conversion_e': '0=Disable\n1=Enable',
                        'encoding': 'enum',
                        'sub_data_name_c': '使能HIF0到 Switch 到Port11/EMAC0',
                        'sub_data_name_e': 'PFE_Mirror0'
                    },
                    {
                        'bit': '3',
                        'byte': '#5',
                        'conversion_c': '0=禁止\n1=使能',
                        'conversion_e': '0=Disable\n1=Enable',
                        'encoding': 'enum',
                        'sub_data_name_c': '使能HIF1到 Switch 到Port11/EMAC0',
                        'sub_data_name_e': 'PFE_Mirror1'
                    },
                    {
                        'bit': '4',
                        'byte': '#5',
                        'conversion_c': '0=禁止\n1=使能',
                        'conversion_e': '0=Disable\n1=Enable',
                        'encoding': 'enum',
                        'sub_data_name_c': '使能HIF2到 Switch 到Port11/EMAC0',
                        'sub_data_name_e': 'PFE_Mirror2'
                    },
                    {
                        'bit': '5',
                        'byte': '#5',
                        'conversion_c': '0=禁止\n1=使能',
                        'conversion_e': '0=Disable\n1=Enable',
                        'encoding': 'enum',
                        'sub_data_name_c': '使能EMAC1到 Switch 到Port11/EMAC0',
                        'sub_data_name_e': 'PFE_Mirror3'
                    },
                    {
                        'bit': '6~7',
                        'byte': '#5',
                        'conversion_c': '-',
                        'conversion_e': '-',
                        'encoding': 'Reserved',
                        'sub_data_name_c': '预留',
                        'sub_data_name_e': 'Reserved'
                    }
                ],
                'routineStatus(Reponse)': [
                    {
                        'bit': '0',
                        'byte': '#5',
                        'conversion_c': '0=成功\n1=失败',
                        'conversion_e': '0=success\n1=fail',
                        'encoding': 'enum',
                        'sub_data_name_c': '使能Port 0~Port 10 + Port 12 + Port 13到OBD Port',
                        'sub_data_name_e': 'Switch_Mirror0'
                    },
                    {
                        'bit': '1',
                        'byte': '#5',
                        'conversion_c': '0=成功\n1=失败',
                        'conversion_e': '0=success\n1=fail',
                        'encoding': 'enum',
                        'sub_data_name_c': '使能Port 11到OBD Port',
                        'sub_data_name_e': 'Switch_Mirror1'
                    },
                    {
                        'bit': '2',
                        'byte': '#5',
                        'conversion_c': '0=成功\n1=失败',
                        'conversion_e': '0=success\n1=fail',
                        'encoding': 'enum',
                        'sub_data_name_c': '使能HIF0到 Switch 到Port11/EMAC0',
                        'sub_data_name_e': 'PFE_Mirror0'
                    },
                    {
                        'bit': '3',
                        'byte': '#5',
                        'conversion_c': '0=成功\n1=失败',
                        'conversion_e': '0=success\n1=fail',
                        'encoding': 'enum',
                        'sub_data_name_c': '使能HIF1到 Switch 到Port11/EMAC0',
                        'sub_data_name_e': 'PFE_Mirror1'
                    },
                    {
                        'bit': '4',
                        'byte': '#5',
                        'conversion_c': '0=成功\n1=失败',
                        'conversion_e': '0=success\n1=fail',
                        'encoding': 'enum',
                        'sub_data_name_c': '使能HIF2到 Switch 到Port11/EMAC0',
                        'sub_data_name_e': 'PFE_Mirror2'
                    },
                    {
                        'bit': '5',
                        'byte': '#5',
                        'conversion_c': '0=成功\n1=失败',
                        'conversion_e': '0=success\n1=fail',
                        'encoding': 'enum',
                        'sub_data_name_c': '使能EMAC1到 Switch 到Port11/EMAC0',
                        'sub_data_name_e': 'PFE_Mirror3'
                    },
                    {
                        'bit': '6~7',
                        'byte': '#5',
                        'conversion_c': '预留',
                        'conversion_e': 'Reserved',
                        'encoding': 'Reserved',
                        'sub_data_name_c': '预留',
                        'sub_data_name_e': 'Reserved'
                    }
                ]
            }
        }
    }
    
    # 使用函数提取数据
    result = extract_routine_data(raw_data)
    if result:
        print("找到 '01:startRoutine' 对应的数据:")
        print(f"键: {list(result.keys())}")
        
        request_array, response_array = get_specific_arrays(raw_data)
        print(f"\nRequest 数组长度: {len(request_array)}")
        print(f"Response 数组长度: {len(response_array)}")
        
        print("\nRequest 数组中的前几个元素示例:")
        for i, item in enumerate(request_array[:2]):  # 只显示前两个元素作为示例
            print(f"  元素 {i+1}: {item}")
            
        print("\nResponse 数组中的前几个元素示例:")
        for i, item in enumerate(response_array[:2]):  # 只显示前两个元素作为示例
            print(f"  元素 {i+1}: {item}")
    else:
        print("未找到 '01:startRoutine' 对应的数据")