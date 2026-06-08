# 🧪 CE-SDS 数据智能解析与拓扑分析系统 (CE-SDS Smart Analyzer)

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/deploy) 
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **专为生物制药领域设计的全自动毛细管电泳（CE-SDS）报告解析工具。**
> 完美融合大模型语义抓取与“自适应拓扑断层算法”，精准应对单抗、双特异性抗体、融合蛋白等复杂色谱形态。严守 Data Integrity（数据完整性）合规底线，让繁琐的人工数据核对成为历史。

---

## 🚀 核心功能与亮点

- **智能非结构化提取**：利用 `pdfplumber` 结合 `DeepSeek LLM`，无视 PDF 表格排版变动，精准提取孔位、峰纯度与面积数据。自带防“LLM 幻觉错位”物理拦截防线。
- **动态拓扑形态识别 (Morphology-Aware)**：
  - **NR (非还原) 模式**：精准切分早出峰/晚出峰主峰，严格执行“主峰后碎片不计入”规则，并自动筛选 `>28s` 的真实 IgG 目标。
  - **R (还原) 模式**：首创**最大时间间隙 (Largest Time Gap)** 聚类算法。无需死板的保留时间阈值，自动寻找拓扑断层，完美切分多 LC/HC 链，并智能识别 `R-MP` 连续多峰形态。
- **NGHC 严谨抗噪防御**：引入强绑定的“动态相对时间窗（HC 前 0.2~1.2s）”与纯度阈值过滤，将假阳性机器噪音降至 0。对于特定批次（如含 `REP` 的样本）开放专属豁免通道。
- **合规与溯源 (Data Integrity)**：
  - 自动拦截并标记低浓度/无效样本（主峰 Area <= 415 填入 `N/A`）。
  - 绝不擅自归一化或篡改仪器原始数据比例。
  - 数据结果自动生成内存级多 Sheet 页 Excel 报表，不留本地痕迹。
- **极简部署**：一键集成 Streamlit，无需本地配置环境，支持云端部署，通过浏览器即可全平台访问。

---

## 🛠️ 安装与使用

### 方式一：网页端直接使用 (推荐)
本项目已适配 Streamlit Community Cloud。你可以直接在网页端上传 PDF 并下载 Excel 报表，无需安装任何代码。
*(部署成功后，可将云端 URL 贴在此处)*

### 方式二：本地运行
如果你希望在本地或公司内网服务器运行，请确保已安装 Python 3.8+。

1. **克隆仓库**
   ```bash
   git clone https://github.com/seventhmoonlight/sumcode.git
   cd sumcode
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **启动系统**
   ```bash
   streamlit run app.py
   ```
   *启动后，浏览器会自动打开 `http://localhost:8501`。*

---

## 🧠 核心架构解耦设计

本系统的卓越鲁棒性得益于**“拓扑判定”与“数值加和”的彻底解耦**：
- **骨架判定层**：使用极其严苛的阈值（如 `> 5.0%`）作为锚点，保证形态学切分（如寻找 LC/HC 最大断层）绝对不受微小碎片噪点干扰。
- **数值加和层**：在判定完形态后，使用独立的宽松阈值（如 `>= 2.0%`）进行纯度加和，确保极小比例的有效链条不被漏算。
通过双轨制架构，系统在应对极端脏数据图谱时依然能保持 100% 的准确加和闭环。

---

## 📂 核心文件说明
- `app.py`: Streamlit 交互界面与业务计算引擎（含自适应拓扑算法）。
- `requirements.txt`: Python 运行环境依赖列表。

---

## 👨‍💻 开发者
**seventhmoonlight** - 专注于生物制药自动化算法与 AI 提效。
*(如果你觉得这个工具极大提升了你的工作效率，欢迎点亮右上角的 ⭐️ Star！)*
