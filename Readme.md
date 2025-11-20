# **GAC诊断工具开发框架指南**

##### **项目概述**

GAC诊断工具是一款基于PyQt5开发的汽车诊断软件，采用现代化的软件架构设计，支持UDS、DoIP、SSH、SFTP、SOME/IP等多种通信协议。本框架旨在提供一套稳定、可扩展、易维护的开发基础。



##### **架构设计**

###### **整体架构概述**

GAC诊断工具采用分层架构和模块化设计，实现了高度的可扩展性和可维护性。整个架构从程序入口到通信底层形成了清晰的调用链。



###### **核心架构模式**

\*\*MVC模式：\*\*模型(Model)-视图(View)-控制器(Controller)分离

\*\*分层架构：\*\*表示层→服务层→数据层

\*\*模块化设计：\*\*功能模块独立开发，动态加载

\*\*依赖注入：\*\*松耦合的组件管理



##### **项目结构**

**GacVccTools/**

**├── main.py                              # 应用入口**

**├── app/**

**│   ├── \_\_init\_\_.py**

**│   ├── core/                           # 核心框架层**

**│   │   ├── \_\_init\_\_.py**

**│   │   ├── application.py             # 应用主类**

**│   │   ├── event\_bus.py               # 事件总线**

**│   │   ├── plugin\_manager.py          # 插件管理器**

**│   │   ├── dependency\_injection.py    # 依赖注入容器**

**│   │   ├── base\_module.py            # 模块基类**

**│   │   ├── base\_service.py           # 服务基类**

**│   │   └── base\_repository.py        # 仓储基类**

**│   ├── common/                        # 公共基础设施层**

**│   │   ├── \_\_init\_\_.py**

**│   │   ├── communication/             # 通信基础设施**

**│   │   │   ├── \_\_init\_\_.py**

**│   │   │   ├── clients/              # 通信客户端实现**

**│   │   │   │   ├── \_\_init\_\_.py**

**│   │   │   │   ├── base\_client.py    # 客户端基类**

**│   │   │   │   ├── uds\_client.py     # UDS客户端**

**│   │   │   │   ├── ssh\_client.py     # SSH客户端**

**│   │   │   │   ├── sftp\_client.py    # SFTP客户端**

**│   │   │   │   └── someip\_client.py  # SOME/IP客户端**

**│   │   │   ├── protocols/            # 协议层实现**

**│   │   │   │   ├── \_\_init\_\_.py**

**│   │   │   │   ├── uds\_protocol.py   # UDS协议处理**

**│   │   │   │   ├── someip\_protocol.py # SOME/IP协议**

**│   │   │   │   └── iso14229.py       # ISO14229标准实现**

**│   │   │   └── transport/            # 传输层实现**

**│   │   │       ├── \_\_init\_\_.py**

**│   │   │       ├── doip\_transport.py # DoIP传输**

**│   │   │       ├── tcp\_transport.py  # TCP传输**

**│   │   │       └── isotp\_transport.py # ISO-TP传输**

**│   │   ├── repositories/             # 数据仓储层**

**│   │   │   ├── \_\_init\_\_.py**

**│   │   │   ├── base\_repository.py    # 仓储基类**

**│   │   │   ├── device\_repository.py  # 设备数据仓储**

**│   │   │   ├── diagnostic\_repository.py # 诊断数据仓储**

**│   │   │   ├── file\_repository.py    # 文件数据仓储**

**│   │   │   └── user\_repository.py    # 用户数据仓储**

**│   │   └── utils/                    # 工具类**

**│   │       ├── \_\_init\_\_.py**

**│   │       ├── validators.py         # 数据验证器**

**│   │       ├── converters.py         # 数据转换器**

**│   │       ├── helpers.py            # 辅助函数**

**│   │       └── constants.py          # 常量定义**

**│   ├── services/                     # 领域服务层**

**│   │   ├── \_\_init\_\_.py**

**│   │   ├── communication/            # 通信服务层（新增核心）**

**│   │   │   ├── \_\_init\_\_.py**

**│   │   │   ├── communication\_service.py # 通信服务门面**

**│   │   │   ├── session\_manager.py    # 会话管理器**

**│   │   │   ├── connection\_pool.py   # 连接池**

**│   │   │   ├── protocol\_adapter.py  # 协议适配器基类**

**│   │   │   └── protocol\_adapters/    # 具体协议适配器**

**│   │   │       ├── \_\_init\_\_.py**

**│   │   │       ├── uds\_adapter.py    # UDS协议适配器**

**│   │   │       ├── diagnostic\_adapter.py # 诊断协议适配器**

**│   │   │       └── ssh\_adapter.py    # SSH协议适配器**

**│   │   ├── device/                   # 设备管理服务**

**│   │   │   ├── \_\_init\_\_.py**

**│   │   │   ├── device\_service.py    # 设备服务**

**│   │   │   ├── topology\_service.py  # 拓扑服务**

**│   │   │   ├── performance\_service.py # 性能监控服务**

**│   │   │   └── status\_service.py     # 状态监控服务**

**│   │   ├── diagnostic/               # 诊断服务**

**│   │   │   ├── \_\_init\_\_.py**

**│   │   │   ├── dtc\_service.py        # DTC诊断服务**

**│   │   │   ├── did\_service.py        # DID数据服务**

**│   │   │   ├── routine\_service.py    # 例程控制服务**

**│   │   │   └── diagnostic\_manager.py # 诊断管理器**

**│   │   ├── file/                     # 文件传输服务**

**│   │   │   ├── \_\_init\_\_.py**

**│   │   │   ├── file\_transfer\_service.py # 文件传输服务**

**│   │   │   ├── file\_parser\_service.py # 文件解析服务**

**│   │   │   ├── download\_manager.py   # 下载管理器**

**│   │   │   └── format\_converter.py   # 格式转换服务**

**│   │   ├── configuration/            # 配置服务**

**│   │   │   ├── \_\_init\_\_.py**

**│   │   │   ├── config\_service.py     # 配置服务**

**│   │   │   ├── log\_config\_service.py # 日志配置服务**

**│   │   │   └── ecu\_config\_service.py # ECU配置服务**

**│   │   ├── update/                   # 升级服务**

**│   │   │   ├── \_\_init\_\_.py**

**│   │   │   ├── software\_update\_service.py # 软件升级服务**

**│   │   │   ├── firmware\_service.py   # 固件服务**

**│   │   │   └── update\_manager.py     # 升级管理器**

**│   │   └── system/                   # 系统服务**

**│   │       ├── \_\_init\_\_.py**

**│   │       ├── logging\_service.py    # 日志服务**

**│   │       ├── config\_service.py     # 系统配置服务**

**│   │       └── backup\_service.py     # 备份服务**

**│   ├── modules/                      # UI模块层（表示层）**

**│   │   ├── \_\_init\_\_.py**

**│   │   ├── auth/                     # 认证模块**

**│   │   │   ├── \_\_init\_\_.py**

**│   │   │   ├── controllers/**

**│   │   │   ├── views/**

**│   │   │   ├── models/**

**│   │   │   └── resources/**

**│   │   ├── device\_management/        # 设备管理模块**

**│   │   │   ├── \_\_init\_\_.py**

**│   │   │   ├── controllers/**

**│   │   │   ├── views/**

**│   │   │   ├── models/**

**│   │   │   └── resources/**

**│   │   ├── diagnostic/               # 诊断模块**

**│   │   │   ├── \_\_init\_\_.py**

**│   │   │   ├── controllers/**

**│   │   │   ├── views/**

**│   │   │   ├── models/**

**│   │   │   └── resources/**

**│   │   ├── file\_transfer/            # 文件传输模块**

**│   │   │   ├── \_\_init\_\_.py**

**│   │   │   ├── controllers/**

**│   │   │   ├── views/**

**│   │   │   ├── models/**

**│   │   │   └── resources/**

**│   │   └── ...                      # 其他模块**

**│   └── presentation/                 # 表示层组件**

**│       ├── \_\_init\_\_.py**

**│       ├── main\_window.py            # 主窗口**

**│       ├── views/                    # 公共视图组件**

**│       └── widgets/                  # 自定义控件**

**├── config/                           # 配置文件**

**├── resources/                        # 资源文件**





##### **架构调用流程图**

**第一步：程序入口（main.py）**

应用程序的入口点，负责初始化应用程序，创建主窗口，并启动事件循环。

**第二步：主窗口（main\_window.py）**

主窗口负责创建用户界面，包括菜单、工具栏、状态栏和中心部件。中心部件通常是一个堆叠窗口（QStackedWidget）或标签页（QTabWidget），用于显示不同模块的视图。

主窗口通过模块管理器（ModuleManager）加载所有启用的模块。模块管理器读取模块配置，动态导入模块，并调用每个模块的初始化方法。

**第三步：模块管理器（ModuleManager）**

模块管理器负责发现、加载和初始化功能模块。每个模块必须实现一个模块类（继承自BaseModule），该模块类负责创建控制器和视图。

**第四步：模块（Module）**

每个功能模块都有一个模块类，它充当模块的入口点。模块类在初始化时创建控制器实例，并通过控制器获取视图。模块类还将控制器和视图暴露给主窗口。

**第五步：控制器（Controller）**

控制器是模块的核心，它处理视图发出的用户交互事件，并调用服务层的方法来执行业务逻辑。控制器还负责将服务层返回的数据更新到视图。

控制器通过依赖注入容器（DependencyInjection）获取服务实例。依赖注入容器负责创建和管理服务实例，并处理服务之间的依赖关系。

**第六步：服务（Service）**

服务层包含业务逻辑，它通过通信服务门面（CommunicationService）与设备进行通信。服务层还负责数据持久化，通过仓储（Repository）模式访问数据库。

**第七步：通信服务门面（CommunicationService）**

通信服务门面提供了一个统一的接口，用于执行各种通信协议（如UDS、SSH、SFTP、SOME/IP等）。它内部使用协议适配器（Protocol Adapter）将通用的通信请求转换为特定协议的请求，并使用连接池（Connection Pool）来管理通信连接。

**第八步：通信客户端（Client）和传输层（Transport）**

通信客户端负责实现特定协议的通信细节。传输层负责底层网络通信，如TCP/IP、DoIP等。



**程序启动流程:**

main.py 

&nbsp;   → GACApplication.run()

&nbsp;       → MainWindow.\_\_init\_\_()

&nbsp;           → ModuleManager.load\_all\_modules()

&nbsp;               → 各模块Module.initialize()

&nbsp;                   → 各模块Controller.initialize()

&nbsp;                       → 各模块View.\_\_init\_\_()

**用户操作流程:**

用户操作 → View事件 

&nbsp;   → Controller业务处理 

&nbsp;       → Service业务逻辑 

&nbsp;           → CommunicationService通信门面

&nbsp;               → 协议适配器 → 通信客户端 → 硬件设备



##### 

##### **完整的调用链示例**

###### 用户操作"刷新设备拓扑"的完整调用链：

用户点击"刷新拓扑"按钮

&nbsp;   → DeviceManagementView.refresh\_button\_clicked()

&nbsp;       → DeviceManagementController.on\_refresh\_topology()

&nbsp;           → DeviceService.get\_device\_topology(device\_id)

&nbsp;               → CommunicationService.get\_device\_topology(device\_id)

&nbsp;                   → CommunicationService.read\_did\_data(device\_id, 0xF190) \[UDS]

&nbsp;                   → CommunicationService.execute\_ssh\_command(device\_id, "uname -a") \[SSH]

&nbsp;                       → UDSAdapter.build\_request()

&nbsp;                       → UDSClient.send\_request()

&nbsp;                           → DoIPTransport.send\_request()

&nbsp;                               → 网络层发送到硬件设备

&nbsp;                       ← 设备响应数据原路返回

&nbsp;                   ← CommunicationService返回组合数据

&nbsp;               ← DeviceService返回拓扑信息

&nbsp;           ← Controller更新视图数据

&nbsp;       ← View刷新界面显示





##### **架构优势总结**

###### **1. 清晰的职责分离**

表示层: 负责UI显示和用户交互

控制层: 协调视图和服务的交互

服务层: 处理业务逻辑

通信层: 管理各种通信协议

数据层: 处理数据持久化

###### **2. 高度可扩展性**

新增协议只需添加新的协议适配器

新增功能模块遵循统一接口规范

服务层可轻松添加新的业务功能

###### **3. 松耦合设计**

依赖注入管理组件依赖关系

门面模式隐藏复杂子系统

适配器模式统一协议接口

###### **4. 易于测试和维护**

各层可独立测试

清晰的接口定义

模块化的错误处理





##### **开发工具推荐**

**IDE:** PyCharm Professional 或 VS Code

**版本控制:** Git



##### **安装步骤**

**克隆代码库**

git clone http://10.99.17.96/atcode/python/oneboxforgac.git



##### **模块开发最佳实践**

**1.遵循单一职责原则**：每个模块只负责一个明确的功能领域

\*\*2.保持接口简洁：\*\*模块对外提供清晰的接口方法

\*\*3.错误处理：\*\*妥善处理异常，提供有意义的错误信息

\*\*4.资源管理：\*\*及时释放资源，避免内存泄漏

\*\*5.信号槽连接：\*\*正确连接和断开信号槽

