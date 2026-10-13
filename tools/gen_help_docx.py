"""
将 VCC 车载测试平台用户帮助文档 Markdown 转换为格式化的 .docx 文件
"""
import re
from docx import Document
from docx.shared import Pt, Inches, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

doc = Document()

# ===== 全局样式设置 =====
style = doc.styles['Normal']
style.font.name = '微软雅黑'
style.font.size = Pt(10.5)
style.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
style.paragraph_format.space_after = Pt(4)
style.paragraph_format.line_spacing = 1.25

# 标题样式
for level in range(1, 5):
    hs = doc.styles[f'Heading {level}']
    hs.font.name = '微软雅黑'
    hs.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    hs.font.color.rgb = RGBColor(0x1A, 0x47, 0x8A)
    hs.font.bold = True

doc.styles['Heading 1'].font.size = Pt(22)
doc.styles['Heading 2'].font.size = Pt(16)
doc.styles['Heading 3'].font.size = Pt(13)
doc.styles['Heading 4'].font.size = Pt(11)

# 列表样式
for ls in ['List Bullet', 'List Number']:
    lst = doc.styles[ls]
    lst.font.name = '微软雅黑'
    lst.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    lst.font.size = Pt(10.5)

# ===== 辅助函数 =====
def set_east_asian_font(run, font_name='微软雅黑'):
    """为 run 设置中文字体"""
    run.font.name = font_name
    r = run._element
    rPr = r.find(qn('w:rPr'))
    if rPr is None:
        rPr = parse_xml(f'<w:rPr {nsdecls("w")}></w:rPr>')
        r.insert(0, rPr)
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = parse_xml(f'<w:rFonts {nsdecls("w")}/>')
        rPr.insert(0, rFonts)
    rFonts.set(qn('w:eastAsia'), font_name)

def add_rich_run(paragraph, text):
    """在段落中添加带格式的 run（处理 **bold** 和 `code`）"""
    pattern = re.compile(r'(\*\*.*?\*\*|`[^`]+`)')
    parts = pattern.split(text)
    for part in parts:
        if not part:
            continue
        if part.startswith('**') and part.endswith('**'):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
            set_east_asian_font(run)
        elif part.startswith('`') and part.endswith('`'):
            run = paragraph.add_run(part[1:-1])
            run.font.name = 'Consolas'
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)
        else:
            run = paragraph.add_run(part)
            set_east_asian_font(run)

def add_para(text, style_name='Normal', bold_prefix=None):
    """添加段落，支持内联格式"""
    p = doc.add_paragraph(style=style_name)
    if bold_prefix:
        run = p.add_run(bold_prefix)
        run.bold = True
        set_east_asian_font(run)
    add_rich_run(p, text)
    return p

def add_bullet(text, level=0):
    """添加无序列表项"""
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.left_indent = Inches(0.25 + level * 0.25)
    add_rich_run(p, text)
    return p

def add_numbered(text, number=None):
    """添加有序列表项"""
    p = doc.add_paragraph(style='List Number')
    add_rich_run(p, text)
    return p

def add_note(text, note_type='tip'):
    """添加提示/注意段落，带左边框"""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.3)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)

    # 添加左边框（通过 XML 设置）
    pPr = p._element.get_or_add_pPr()
    pBdr = parse_xml(
        f'<w:pBdr {nsdecls("w")}>'
        f'  <w:left w:val="single" w:sz="12" w:space="8" '
        f'    w:color="{"E67E22" if note_type == "warn" else "2E86C1"}"/>'
        f'</w:pBdr>'
    )
    pPr.append(pBdr)

    # 添加底纹背景
    shd = parse_xml(
        f'<w:shd {nsdecls("w")} w:fill="{"FEF5E7" if note_type == "warn" else "EBF5FB"}" w:val="clear"/>'
    )
    pPr.append(shd)

    # 图标和文本
    icon = '⚠️' if note_type == 'warn' else '💡'
    prefix = '注意：' if note_type == 'warn' else '提示：'
    run = p.add_run(f'{icon} {prefix}')
    run.bold = True
    run.font.size = Pt(10)
    set_east_asian_font(run)

    clean = re.sub(r'^\*\*.*?\*\*[：:]\s*', '', text)
    add_rich_run(p, clean)
    return p

def set_cell_shading(cell, color):
    """设置单元格背景色"""
    tc = cell._element
    tcPr = tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color}" w:val="clear"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=40, bottom=40, left=80, right=80):
    """设置单元格内边距"""
    tc = cell._element
    tcPr = tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'  <w:top w:w="{top}" w:type="dxa"/>'
        f'  <w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'  <w:left w:w="{left}" w:type="dxa"/>'
        f'  <w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)

def add_table(headers, rows):
    """添加格式化表格"""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # 设置表格边框
    tbl = table._element
    tblPr = tbl.find(qn('w:tblPr'))
    if tblPr is None:
        tblPr = parse_xml(f'<w:tblPr {nsdecls("w")}></w:tblPr>')
        tbl.insert(0, tblPr)
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'  <w:top w:val="single" w:sz="4" w:space="0" w:color="BDC3C7"/>'
        f'  <w:left w:val="single" w:sz="4" w:space="0" w:color="BDC3C7"/>'
        f'  <w:bottom w:val="single" w:sz="4" w:space="0" w:color="BDC3C7"/>'
        f'  <w:right w:val="single" w:sz="4" w:space="0" w:color="BDC3C7"/>'
        f'  <w:insideH w:val="single" w:sz="4" w:space="0" w:color="BDC3C7"/>'
        f'  <w:insideV w:val="single" w:sz="4" w:space="0" w:color="BDC3C7"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)

    # 表头
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ''
        p = cell.paragraphs[0]
        run = p.add_run(h)
        run.bold = True
        run.font.size = Pt(9.5)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        set_east_asian_font(run)
        set_cell_shading(cell, '1A478A')
        set_cell_margins(cell)

    # 数据行（斑马纹）
    for ri, row in enumerate(rows):
        bg_color = 'F8F9FA' if ri % 2 == 0 else 'FFFFFF'
        for ci, val in enumerate(row):
            cell = table.rows[ri + 1].cells[ci]
            cell.paragraphs[0].clear()
            add_rich_run(cell.paragraphs[0], val)
            for run in cell.paragraphs[0].runs:
                run.font.size = Pt(9)
                set_east_asian_font(run)
            set_cell_shading(cell, bg_color)
            set_cell_margins(cell)

    doc.add_paragraph()  # 表后留白
    return table

def add_code_block(text):
    """添加代码块（灰色背景段落）"""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.3)
    p.paragraph_format.right_indent = Inches(0.3)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)

    # 添加灰色背景
    pPr = p._element.get_or_add_pPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="F2F3F4" w:val="clear"/>')
    pPr.append(shd)

    run = p.add_run(text)
    run.font.name = 'Consolas'
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x2C, 0x3E, 0x50)
    return p

def add_image(image_path, width_inches=6.0, caption=None):
    """添加图片"""
    import os
    if not os.path.exists(image_path):
        print(f"警告：图片不存在 {image_path}")
        return None
    
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(8)
    
    run = p.add_run()
    run.add_picture(image_path, width=Inches(width_inches))
    
    if caption:
        cap_p = doc.add_paragraph()
        cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap_run = cap_p.add_run(caption)
        cap_run.font.size = Pt(9)
        cap_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        cap_run.italic = True
        set_east_asian_font(cap_run)
    
    return p

def add_section_title(text):
    """添加小节标题（加粗蓝色）"""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(0x1A, 0x47, 0x8A)
    set_east_asian_font(run)
    return p

# ===== 生成文档内容 =====

# 封面标题
title = doc.add_heading('VCC 车载测试平台', level=0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
for run in title.runs:
    run.font.color.rgb = RGBColor(0x1A, 0x47, 0x8A)
    set_east_asian_font(run)

subtitle = doc.add_paragraph()
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = subtitle.add_run('用户帮助文档  v1.0')
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
set_east_asian_font(run)

doc.add_paragraph()  # 空行

# ===== 一、软件概述 =====
doc.add_heading('一、软件概述', level=1)
add_para('VCC（Vehicle Communication & Configuration）车载测试平台是一款面向汽车电子控制单元（ECU）的综合诊断测试工具。'
         '软件基于 UDS（ISO 14229）、DoIP（ISO 13400）、SomeIP 等车载网络协议，提供设备管理、故障诊断、数据读写、固件升级、'
         '文件传输等核心功能，适用于 ECU 开发、集成测试及产线诊断等场景。')

doc.add_heading('系统要求', level=3)
add_bullet('**操作系统**：Windows 10/11（64 位）')
add_bullet('**网络接口**：以太网口（用于 DoIP / SomeIP 通信）')
add_bullet('**运行环境**：已打包为独立安装程序，无需额外安装 Python 环境')

doc.add_heading('启动与激活', level=3)
add_numbered('双击桌面快捷方式或运行 VCC_Setup_1.0.0.exe 安装后启动')
add_numbered('首次启动将弹出激活窗口，需输入激活码完成授权')
add_numbered('授权到期前 15 分钟软件将弹窗提醒，到期后应用自动锁定，需重新激活')
add_note('软件采用单实例模式，同一台电脑仅允许运行一个 VCC 实例。')

# ===== 二、主界面布局 =====
doc.add_heading('二、主界面布局', level=1)
add_para('启动完成后，主界面由以下区域组成：')
add_table(
    ['区域', '说明'],
    [
        ['**左侧导航树**', '按功能分组展示所有模块入口，点击即可打开对应功能页签'],
        ['**顶部搜索栏**', '支持模糊搜索所有功能页面名称，快速跳转'],
        ['**中央工作区**', 'Tab 页签式工作区，每个功能模块以独立 Tab 展示，支持关闭/关闭其他/关闭所有'],
        ['**底部状态栏**', '显示性能摘要（在线设备数、CPU/内存占用等）'],
        ['**欢迎页**', '无 Tab 时显示欢迎页，提供常用功能快捷入口'],
    ]
)

doc.add_heading('导航分组', level=3)
nav_text = (
    '🏎️ 设备管理\n'
    '    📁 设备管理 | 📊 拓扑监控 | ⚙️ 性能监控 | ⏰ 时钟管理\n'
    '🛠 诊断功能\n'
    '    ⚠️ DTC故障诊断 | 🔍 DID数据管理 | 🧪 UDS指令编排\n'
    '📂 文件管理\n'
    '    🔄 文件传输中心 | 📥 日志文件下载 | 📡 总线数据下载\n'
    '🚀 设备升级\n'
    '    🚗 设备升级\n'
    '⚙️ 配置中心\n'
    '    📝 日志配置 | 🔧 常用配置\n'
    '🌐 Someip功能\n'
    '    🌐 服务发现信息面板 | 🌐 报文解析界面'
)
add_code_block(nav_text)

# 添加主界面截图
add_image(
    r'd:\VCC\tools\screenshots\main_interface.png',
    width_inches=6.5,
    caption='图 2-1 VCC 车载测试平台主界面'
)

# ===== 三、功能模块详解 =====
doc.add_heading('三、功能模块详解', level=1)

# --- 3.1 设备管理 ---
doc.add_heading('3.1 📁 设备管理', level=2)
add_para('设备管理是 VCC 的核心基础模块，负责 ECU 设备的添加、编辑、删除和多协议连接管理。')

add_section_title('操作步骤')
add_numbered('点击左侧导航树「设备管理」打开页签')
add_numbered('在页面左侧表单填写设备信息（设备名、类型、DoIP/SomeIP/SSH 配置）')
add_numbered('点击「添加设备」按钮，设备出现在右侧列表')
add_numbered('选中设备 → 点击工具栏 DoIP 按钮连接 → 状态变为 🟢 在线')
add_numbered('再点击 SSH 按钮连接 SSH（依赖 DoIP 已连接）')
add_numbered('点击 SomeIP 按钮连接 SomeIP')

doc.add_heading('添加设备', level=4)
add_para('在设备管理页面左侧填写设备信息：')
add_table(
    ['字段', '说明', '默认值'],
    [
        ['设备名', '自定义名称（必填）', '—'],
        ['设备类型', 'ECU / 网关 / 域控 / 其他', 'ECU'],
        ['DoIP IP', '设备 DoIP 地址', '—'],
        ['DoIP 端口', 'DoIP 端口号', '13400'],
        ['SomeIP IP', 'SomeIP 通信地址', '—'],
        ['标准组播 IP', 'SomeIP SD 组播地址', '239.71.0.2'],
        ['标准组播端口', 'SomeIP SD 端口', '30490'],
        ['VLAN ID', 'VLAN 标识', '4'],
        ['客户端端口', 'SomeIP 客户端端口', '30813'],
        ['客户端 ID', 'SomeIP 客户端 ID', '30813'],
        ['SSH IP', 'SSH 登录地址', '—'],
        ['SSH 端口', 'SSH 端口号', '22'],
        ['用户名', 'SSH 用户名', '—'],
        ['密码', 'SSH 密码', '—'],
    ]
)

add_section_title('注意事项')
add_note('连接顺序：必须先连接 DoIP，再连接 SSH。', 'warn')
add_note('每个协议同时只允许一个设备连接。')
add_note('删除设备前必须断开所有协议连接，否则无法删除。')
add_note('连接超时 15 秒自动取消，避免 UI 卡死。')
add_note('编辑设备时可点击 ⚙ 按钮进入高级设置（DoIP/诊断层/SomeIP 参数）。')

doc.add_heading('连接状态颜色标识', level=4)
add_bullet('🟢 **在线/建链成功** — 协议已连接')
add_bullet('🔴 **已断开/未连接** — 协议未连接')
add_bullet(' **连接中** — 正在建立连接')

add_note('提示：连接状态会实时刷新，颜色变化直观显示设备连接状态。')

doc.add_heading('快捷操作', level=4)
add_table(
    ['工具栏按钮', '功能'],
    [
        ['DoIP', '连接/断开 DoIP'],
        ['SSH', '连接/断开 SSH'],
        ['SomeIP', '连接/断开 SomeIP'],
        ['✏️', '编辑设备信息'],
        ['🗑️', '删除设备'],
        ['🚗', '跳转到设备升级页面'],
        ['🔍', '跳转到拓扑监控页面'],
    ]
)

add_note('提示：快捷按钮位于设备列表上方工具栏，选中设备后点击对应按钮即可操作。')

# --- 3.2 拓扑监控 ---
doc.add_heading('3.2 📊 拓扑监控', level=2)
add_para('拓扑监控页面以可视化方式展示已连接设备的网络拓扑状态，实时显示设备在线状态和链路信息。')

add_section_title('操作步骤')
add_numbered('点击左侧「拓扑监控」打开页签')
add_numbered('或通过设备管理页面 🔍 快捷按钮跳转，自动聚焦目标设备')
add_numbered('查看设备拓扑图和在线状态，自动刷新')

add_section_title('注意事项')
add_note('需先有设备连接才会显示拓扑图。')

# --- 3.3 性能监控 ---
doc.add_heading('3.3 ⚙️ 性能监控', level=2)
add_para('性能监控页面通过 SSH 协议实时采集 ECU 的系统性能数据：')
add_bullet('**CPU 使用率**：实时监控处理器负载')
add_bullet('**内存使用率**：RAM 占用情况')
add_bullet('**磁盘 I/O**：磁盘读写状态')
add_bullet('**进程列表**：ECU 上运行的进程信息')

add_section_title('操作步骤')
add_numbered('确保目标设备 SSH 已连接')
add_numbered('点击左侧「性能监控」打开页签')
add_numbered('点击开始采集，实时查看 CPU/内存/磁盘/进程数据')
add_numbered('支持导出数据文件供离线分析')

add_section_title('注意事项')
add_note('仅依赖 SSH 连接，无需 DoIP。')
add_note('采集频率会影响 ECU 性能，建议合理设置采集间隔。', 'warn')

# --- 3.4 时钟管理 ---
doc.add_heading('3.4 ⏰ 时钟管理', level=2)
add_para('时钟管理模块用于读取和管理 ECU 系统时间：')
add_bullet('实时读取 ECU 系统时间（通过 SSH 执行 `date` 命令）')
add_bullet('显示时区信息和系统运行时间（uptime）')
add_bullet('每秒自动刷新，支持与本机时间对比')

add_section_title('操作步骤')
add_numbered('确保设备 SSH 已连接')
add_numbered('打开时钟管理页面，自动显示 ECU 系统时间')
add_numbered('查看时区和 uptime 信息，与本机时间对比')
add_numbered('页面每秒自动刷新数据')

add_section_title('注意事项')
add_note('仅依赖 SSH 连接。')
add_note('时间数据通过 SSH 执行 `date` 命令获取。')

# --- 3.5 DTC 故障诊断 ---
doc.add_heading('3.5 ⚠️ DTC 故障诊断', level=2)
add_para('DTC（Diagnostic Trouble Code）故障诊断模块用于读取、分析和管理 ECU 故障码。')

add_section_title('操作步骤')
add_numbered('确保设备 DoIP 已连接')
add_numbered('点击「读取故障码」按钮')
add_numbered('查看故障码列表，通过 Tab 切换全部/当前/历史/未决分类')
add_numbered('选中某个故障码 → 点击「读取冻结帧」查看详细数据')
add_numbered('点击「清除故障码」清空所有故障')
add_numbered('使用搜索框按 DTC 编码或描述过滤')
add_numbered('点击表头可按升序/降序/默认三态排序')

doc.add_heading('故障分类', level=4)
add_table(
    ['分类', '说明'],
    [
        ['全部故障', '所有故障码'],
        ['当前故障', 'Status Bit 0 = 1，当前正在发生的故障'],
        ['历史故障', 'Status Bit 3 = 1，已确认的历史故障'],
        ['未决故障', 'Status Bit 2 = 1，尚未确认的间歇性故障'],
    ]
)

add_section_title('注意事项')
add_note('需要加载 DPT 文件才能显示中文故障描述。', 'warn')
add_note('Status Bit 含义：Bit0=当前故障、Bit2=未决故障、Bit3=历史故障。')
add_note('故障码列表自动保存，重启软件后恢复。')
add_note('冻结帧解析依赖 DPT 配置。')
add_note('提示：读取故障码前请确保 ECU 处于默认会话状态，否则可能读取失败。')
add_note('提示：清除故障码操作不可逆，请确认后再执行。', 'warn')

# --- 3.6 DID 数据管理 ---
doc.add_heading('3.6 🔍 DID 数据管理', level=2)
add_para('DID（Data Identifier）数据管理模块用于读取和写入 ECU 数据标识符。')

add_section_title('操作步骤')
add_numbered('确保 DoIP 已连接')
add_numbered('在 DID 输入框中输入地址（如 `F190` 或 `22F190`）')
add_numbered('点击读取按钮查看结果')
add_numbered('写入 DID：输入数据 → 点击写入 → 自动执行安全访问流程（Seed & Key）')
add_numbered('加载 DPT 文件后自动解析原始数据为可读字段')
add_numbered('支持数据持久化和历史记录')

add_section_title('注意事项')
add_note('写入操作会自动触发安全访问（Seed & Key），需确保 ECU 支持。', 'warn')
add_note('需要 DPT 文件才能解析 DID 数据含义。')
add_note('支持批量读取多个 DID 地址。')
add_note('提示：DID 地址可以带前缀 22 或不带，系统会自动识别。')
add_note('提示：写入数据前请确认 DID 为可写类型，只读 DID 写入会失败。', 'warn')

# --- 3.7 UDS 指令编排 ---
doc.add_heading('3.7 🧪 UDS 指令编排', level=2)
add_para('UDS 指令编排模块允许用户自定义 UDS 诊断指令序列并批量执行。')

add_section_title('操作步骤')
add_numbered('在指令表格逐行添加 UDS 请求（Hex 格式）')
add_numbered('设置指令名称、请求报文、期望响应')
add_numbered('可插入延时指令（⏱，单位毫秒）')
add_numbered('勾选/取消勾选控制是否执行该行')
add_numbered('设置循环次数，选择是否「失败时停止」')
add_numbered('点击执行，逐条发送并记录响应')
add_numbered('支持导入/导出 JSON 配置文件')

add_section_title('注意事项')
add_note('请求报文必须为合法 Hex 格式。', 'warn')
add_note('建议先用单条指令测试连通性再批量执行。')
add_note('前提条件：DoIP 已连接。')

# --- 3.8 文件传输中心 ---
doc.add_heading('3.8 🔄 文件传输中心', level=2)
add_para('文件传输中心通过 SCP/SFTP 协议实现本机与 ECU 之间的文件双向传输。')

add_section_title('操作步骤')
add_numbered('确保 SSH 已连接（需先连接 DoIP）')
add_numbered('打开文件传输页面')
add_numbered('左侧浏览本地文件，右侧浏览 ECU 远程文件系统')
add_numbered('选择文件 → 点击上传/下载')
add_numbered('查看实时传输进度和速度')

add_section_title('注意事项')
add_note('依赖 SSH 连接（SSH 依赖 DoIP 先连接）。', 'warn')
add_note('大文件传输时请保持网络稳定，避免传输中断。')

# --- 3.9 日志文件下载 ---
doc.add_heading('3.9 📥 日志文件下载', level=2)
add_para('日志文件下载模块用于从 ECU 批量下载日志文件。')

add_section_title('操作步骤')
add_numbered('确保 SSH 已连接')
add_numbered('打开日志下载页面，搜索 ECU 上的日志文件')
add_numbered('支持分页浏览和排序')
add_numbered('单文件下载或勾选多个文件批量下载')
add_numbered('选择本地保存目录，查看下载进度')
add_numbered('支持取消正在下载的任务')

add_section_title('注意事项')
add_note('仅依赖 SSH 连接。')
add_note('批量下载时建议分批进行，避免占用过多资源。')

# --- 3.10 总线数据下载 ---
doc.add_heading('3.10 📡 总线数据下载', level=2)
add_para('总线数据下载模块用于从 ECU 下载总线通信数据（如 CAN 报文记录等），通过 SSH 通道进行文件传输。')

add_section_title('操作步骤')
add_numbered('确保 SSH 已连接')
add_numbered('通过顶部下拉框选择总线数据目录类型（CAN/Ethernet 等）')
add_numbered('按文件名关键字或类型（Type）搜索过滤')
add_numbered('支持翻页和调整每页显示条数')
add_numbered('勾选文件 → 点击批量下载（最多 3 个并行）')
add_numbered('查看实时下载进度和传输速度')
add_numbered('支持取消单个或批量取消下载')

add_section_title('注意事项')
add_note('批量下载最多支持 3 个文件并行传输。', 'warn')
add_note('依赖 SSH 连接（SSH 依赖 DoIP 先连接）。')
add_note('点击表头可按不同字段排序。')

# --- 3.11 设备升级 ---
doc.add_heading('3.11 🚗 设备升级', level=2)
add_para('设备升级模块支持 ECU 固件的在线刷写（OTA），遵循 UDS 刷写流程。')

add_section_title('操作步骤（常规升级）')
add_numbered('确保 DoIP 已连接')
add_numbered('点击浏览按钮选择升级包文件（.zip / .bin），支持拖拽文件')
add_numbered('加载对应的 JSON 升级配置文件')
add_numbered('点击「开始升级」')
add_numbered('系统自动执行完整刷写流程（见刷写流程图）')
add_numbered('等待升级完成，ECU 自动复位')
add_numbered('升级完成后查看操作日志确认结果')

doc.add_heading('刷写流程（自动执行）', level=4)
flash_steps = (
    '等待 ECU 就绪\n'
    '→ 读取 DID（F17F/F180/F187/F189）版本校验\n'
    '→ 进入默认会话 (10 01)\n'
    '→ 进入扩展会话 (10 03)\n'
    '→ 安全访问 (27 21/22)\n'
    '→ 检查下载预条件 (31 01 21 01)\n'
    '→ 请求下载 (38 01)\n'
    '→ 传输数据 (36, 分块传输)\n'
    '→ 传输结束 (37)\n'
    '→ 校验文件 (31 01 21 02, SHA256)\n'
    '→ 擦除/合并 (31 01 21 05)\n'
    '→ 重新认证\n'
    '→ 安装 (31 01 21 03)\n'
    '→ 轮询安装进度 (22 21 04)\n'
    '→ ECU 复位 (11 01)'
)
add_code_block(flash_steps)

doc.add_heading('压测模式', level=4)
add_para('配置多组「升级包+配置文件」任务 → 设置循环次数 → 自动重复升级，每轮自动处理 ECU 复位和重连。')

add_section_title('注意事项')
add_note('升级期间其他模块的 DoIP 请求会被自动拦截（升级屏障），升级完成后自动解除。', 'warn')
add_note('升级过程中不可中断，请保持网络稳定，勿关闭软件。', 'warn')
add_note('必须同时提供升级包和 JSON 配置文件。')
add_note('支持 TesterPresent (3E) 心跳自动管理，防止会话超时。')
add_note('提示：升级前建议备份当前固件版本，以便回滚。', 'warn')
add_note('提示：升级过程中请勿操作其他功能模块，避免干扰刷写流程。', 'warn')
add_note('提示：如果升级失败，请查看操作日志中的错误信息，排查网络或配置文件问题。')

# --- 3.12 日志配置 ---
doc.add_heading('3.12 📝 日志配置', level=2)
add_para('日志配置模块用于管理 ECU 和应用的日志等级配置，分为三个功能区：')

add_section_title('ECU 日志配置步骤')
add_numbered('确保 DoIP 已连接')
add_numbered('从下拉列表选择目标 ECU（支持多选）')
add_numbered('选择日志等级（DEBUG/INFO/WARN/ERROR）')
add_numbered('点击「执行」→ 系统通过 UDS DID 写入方式下发到 ECU')
add_numbered('执行完成后自动回读并刷新 ECU 状态表格，确认配置生效')
add_numbered('查看操作日志确认写入结果')

add_section_title('应用日志配置（CCUA）步骤')
add_numbered('确保 SSH 已连接')
add_numbered('从 ECU 读取应用日志配置列表')
add_numbered('按 ECU ID / APP ID / 日志等级筛选，支持分页浏览')
add_numbered('修改单个或批量修改 CCUA 应用日志等级')
add_numbered('系统弹窗询问是否重启 CCU')
add_numbered('选择「是」立即重启 CCU 使配置生效')

add_section_title('导入配置文件')
add_para('点击「导入映射文件」按钮，选择 `process_log_config_map.json` 文件。')

add_section_title('恢复默认配置')
add_para('支持恢复 CCUA/CCU0/CCU1 默认配置，可删除 `/log` 目录下 DLT 日志文件。')

add_section_title('注意事项')
add_note('ECU 日志配置依赖 DoIP，应用日志配置和恢复操作依赖 SSH。', 'warn')
add_note('修改 CCUA 应用日志后需重启 CCU 才能生效。')
add_note('恢复默认配置会删除 /log 目录下所有 DLT 日志文件。', 'warn')
add_note('恢复 CCUA 配置后可自动触发 CCU 重启并等待重连（最长 120 秒）。')
add_note('提示：导入映射文件后，应用日志配置列表会自动刷新。')
add_note('提示：如果重启 CCU 后 SSH 断开，请等待 120 秒后重新连接。', 'warn')

# --- 3.13 常用配置 ---
doc.add_heading('3.13 🔧 常用配置', level=2)
add_para('常用配置模块提供软件全局诊断参数和协议配置，分为多个子页面：')

add_section_title('操作步骤')
add_numbered('打开常用配置页面')
add_numbered('**DoIP 设置**：选择本机网卡（多网卡时必须选对）、配置连接超时参数')
add_numbered('**诊断层参数**：设置 S3 客户端定时器（影响 3E 发送频率）、P2/P2* 超时')
add_numbered('**服务配置导入**：导入 JSON 配置文件，加载 2E/31 服务定义，支持分页浏览')
add_numbered('**SomeIP 配置**：SomeIP 协议相关参数设置')
add_numbered('修改完成后点击「保存」按钮使配置生效')

add_section_title('注意事项')
add_note('多网卡环境下必须选择正确的网卡，否则 DoIP 无法连通。', 'warn')
add_note('S3 定时器影响 TesterPresent (3E) 发送频率，设置不当会导致会话超时。')
add_note('当系统检测到本机网络接口与 ECU 不在同一网段时，会在操作日志中提示并提供跳转链接。')
add_note('提示：修改诊断层参数后，需要重新连接 DoIP 才能生效。', 'warn')
add_note('提示：服务配置文件导入后，DID 写入和例程控制功能会自动使用新的配置。')

# --- 3.14 服务发现信息面板 ---
doc.add_heading('3.14 🌐 服务发现信息面板', level=2)
add_para('SomeIP SD（Service Discovery）信息面板用于展示 SomeIP 服务发现报文信息：')

add_section_title('操作步骤')
add_numbered('确保 SomeIP 连接已建立')
add_numbered('打开服务发现信息面板')
add_numbered('实时查看 SomeIP SD 报文、服务注册/注销事件')
add_numbered('查看服务实例、端口、协议等详细信息')

add_section_title('注意事项')
add_note('服务发现面板依赖 SomeIP 连接。')
add_note('提示：SomeIP SD 报文会实时刷新，建议先过滤感兴趣的服务 ID。')
add_note('提示：服务注册事件表示 ECU 上线，注销事件表示 ECU 下线。')

# --- 3.15 报文解析界面 ---
doc.add_heading('3.15 🌐 报文解析界面', level=2)
add_para('报文解析界面用于解析 SomeIP 报文内容：')

add_section_title('操作步骤')
add_numbered('加载报文文件（支持拖拽文件到界面）')
add_numbered('自动解析 SomeIP 消息头和载荷')
add_numbered('通过 DPT 配置自动解析载荷含义')
add_numbered('实时展示解析结果')

add_section_title('注意事项')
add_note('报文解析界面为离线分析工具，无需连接即可使用。')
add_note('需要 DPT 文件才能完整解析载荷含义。')
add_note('提示：支持拖拽 pcap 或二进制文件到界面快速加载。')
add_note('提示：解析结果支持导出为文本文件供后续分析。')

# ===== 四、DPT 配置管理 =====
doc.add_heading('四、DPT 配置管理', level=1)
add_para('DPT（Diagnostic Parameter Table）是诊断参数表，VCC 通过加载 DPT 文件实现：')
add_bullet('**DTC 故障描述**：自动匹配故障码中文含义')
add_bullet('**DID 数据解析**：按定义解析 DID 原始数据为可读字段')
add_bullet('**冻结帧解析**：解析冻结帧中的 DID 数据')
add_bullet('软件启动时自动加载上次使用的 DPT 文件，可在常用配置中重新选择')

# ===== 五、搜索与导航 =====
doc.add_heading('五、搜索与导航', level=1)
add_section_title('操作步骤')
add_numbered('在顶部搜索栏输入关键字')
add_numbered('下拉列表实时显示匹配的功能页面')
add_numbered('使用上下方向键选择，回车键跳转')
add_numbered('按 Esc 关闭搜索结果')
add_bullet('设备管理页面提供"升级"和"查询"快捷按钮，可一键跳转')
add_bullet('跳转时自动携带当前选中设备信息')

# ===== 六、操作日志 =====
doc.add_heading('六、操作日志', level=1)
add_para('每个功能模块底部均有 **操作日志** 区域：')
add_bullet('实时显示当前操作的请求和响应报文（Hex 格式）')
add_bullet('记录操作结果和错误信息')
add_bullet('部分日志中包含蓝色超链接，点击可快速跳转到相关设置页面')

# ===== 七、Tab 管理 =====
doc.add_heading('七、Tab 管理', level=1)
add_bullet('**关闭 Tab**：点击 Tab 标签上的 ✕ 按钮，或右键菜单选择')
add_bullet('右键菜单：**关闭当前** | **关闭其他** | **关闭所有**')

# ===== 八、授权管理 =====
doc.add_heading('八、授权管理', level=1)
add_bullet('软件采用激活码授权机制')
add_bullet('授权信息可在 **配置中心 > 常用配置** 中查看')
add_bullet('授权到期前 15 分钟弹窗提醒')
add_bullet('授权过期后应用锁定，需重新激活才能继续使用')

# ===== 九、常见问题（FAQ）=====
doc.add_heading('九、常见问题（FAQ）', level=1)

faqs = [
    ('Q1：连接 DoIP 失败怎么办？',
     '1. 检查网线是否插好，本机与 ECU 是否在同一网段\n'
     '2. 进入常用配置 > DoIP 设置，确认已选择正确的网络接口\n'
     '3. 查看操作日志中的错误信息'),
    ('Q2：SSH 连接提示"请先连接 DoIP"？',
     'SSH 依赖 DoIP 通道，请先确保 DoIP 连接成功（状态显示"建链成功/在线"），再连接 SSH。'),
    ('Q3：升级过程中其他功能无法使用？',
     '这是正常现象。升级期间系统会激活"升级屏障"，自动拦截其他模块的 DoIP 诊断请求，防止干扰刷写流程。升级完成后自动解除。'),
    ('Q4：DTC/DID 页面提示"DPT 解析未完成"？',
     '需要加载 DPT 配置文件。进入常用配置选择正确的 DPT Excel 文件。'),
    ('Q5：软件启动时显示"授权已过期"？',
     '请重新生成激活码并在弹出的激活窗口中输入，完成重新激活后即可继续使用。'),
    ('Q6：连接超时怎么办？',
     '系统设置了 15 秒连接超时保护。超时后会自动取消连接并重置状态，您可以检查网络后重新连接。'),
    ('Q7：日志配置修改后为什么没有生效？',
     '日志配置修改通过 SSH 写入 ECU 配置文件，修改后需要重启 CCU 才能生效。'),
    ('Q8：文件传输/日志下载提示"设备未连接"？',
     '文件传输和日志下载依赖 SSH 通道。请先确保设备 DoIP 和 SSH 均已连接成功。'),
    ('Q9：升级时提示"配置文件未找到"？',
     '常规升级需要同时指定升级包文件和 JSON 配置文件。请确保配置文件路径正确且文件存在。'),
    ('Q10：如何查看软件授权信息？',
     '进入配置中心 > 常用配置，可查看当前授权状态、激活码和到期时间。'),
]

for q, a in faqs:
    p = doc.add_paragraph()
    run = p.add_run(q)
    run.bold = True
    run.font.size = Pt(11)
    set_east_asian_font(run)
    p2 = doc.add_paragraph(a)
    p2.paragraph_format.left_indent = Inches(0.2)

# ===== 十、键盘快捷操作 =====
doc.add_heading('十、键盘快捷操作', level=1)
add_table(
    ['快捷键', '说明'],
    [
        ['搜索栏内输入关键字', '实时搜索功能页面'],
        ['↑ / ↓', '在搜索结果列表中上下移动'],
        ['Enter', '确认选择搜索结果并跳转'],
        ['Esc', '关闭搜索结果下拉列表'],
    ]
)

# ===== 十一、配置文件说明 =====
doc.add_heading('十一、配置文件说明', level=1)
add_table(
    ['配置文件/目录', '位置', '说明'],
    [
        ['设备列表', 'AppData/device_config.json', '保存已添加的设备信息和连接参数'],
        ['DTC 列表', 'AppData/DTC/dtc_list.json', '缓存最近一次读取的故障码'],
        ['DID 列表', 'AppData/DID/did_list.json', '缓存 DID 数据'],
        ['升级配置', 'AppData/DeviceUpgrade/upgrade_config.json', '保存升级包和配置文件路径'],
        ['DPT 路径', 'AppData/DPT 相关配置', '记录上次加载的 DPT 文件路径'],
    ]
)
add_note('配置文件位于用户 AppData 目录下，卸载软件不会自动清除，如需彻底清理请手动删除。')

# ===== 页脚 =====
doc.add_paragraph()
footer = doc.add_paragraph()
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = footer.add_run('文档版本：v1.0 | 最后更新：2026-06-25')
run.font.size = Pt(9)
run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
set_east_asian_font(run)

# ===== 保存 =====
output_path = r'D:\UID01728\Desktop\VCC 车载测试平台 用户帮助文档.docx'
doc.save(output_path)
print(f'文档已保存至: {output_path}')
