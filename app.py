import streamlit as st
import pdfplumber
import pandas as pd
import json
import re
from openai import OpenAI
import concurrent.futures
import io
from decimal import Decimal, ROUND_HALF_UP

# 页面配置
st.set_page_config(page_title="CE-SDS 自动提取器", page_icon="🧪", layout="centered")

# 配置默认 DeepSeek API
DEFAULT_API_KEY = "sk-3c1f8c2176694867999798d821f5c214"

def parse_page_with_llm(client, page_num, page_text):
    prompt = """
    你是一个数据提取专家。以下是 CE-SDS (LabChip) 报告其中一页的纯文本。
    请从中提取样品信息和完整的峰列表（Peak Table）。
    
    要求提取的字段：
    1. "Sample Name": 样品名称（通常在图谱标题方括号之后，或者表格中第一列）
    2. "Vial": 进样孔位（通常在图谱标题方括号内，如 [.../A2] 中的 A2）
    3. "Peaks": 一个数组，包含该样品所有的峰。每个峰包含 "Purity" (纯度%，数字，如果为空请设为0), "Migration Time" (保留时间，数字), 和 "Area" (对应的 "Corr. Area" 面积数值，数字)。
    
    【⚠️极其重要的提取规则⚠️】：
    - 第一行的峰通常是系统峰(Lower Marker)，它的 "% Purity" 栏往往是**空的**，只有 "Corr. Area"。
    - 如果遇到 "% Purity" 为空，请直接跳过该峰，或者将该峰的 Purity 设为 0。
    - **绝对不要**把 "Corr. Area" 的数值 (如几百、上千的大数字) 错填到 "Purity" 中！真正的 Purity 不可能超过 100%！
    
    请返回严格的 JSON 格式（不要包含任何其他说明文字，不要 markdown 标记）。
    示例格式：
    {
        "Sample Name": "RS201801-RM05 Rep1 NR",
        "Vial": "A2",
        "Peaks": [
            {"Purity": 0.0, "Migration Time": 12.75, "Area": 737.64},
            {"Purity": 0.57, "Migration Time": 19.96, "Area": 12.5},
            {"Purity": 97.99, "Migration Time": 31.15, "Area": 2100.5}
        ]
    }
    如果这一页文本中不包含峰列表数据，请返回纯文本的 null。
    """
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"页面文本如下：\n{page_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        result = response.choices[0].message.content
        if result.strip() == 'null':
            return page_num, None
        return page_num, json.loads(result)
    except Exception as e:
        return page_num, None

def format_result_value(value):
    if isinstance(value, str):
        return value
    if pd.isna(value):
        return value
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return value

def round_half_up_1(value):
    return float(Decimal(str(value)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))

# UI 标题与说明
st.title("🧪 LabChip CE-SDS 数据自动提取工具")
st.markdown("""
这款工具专为非技术人员设计！只需上传仪器的 PDF 报告，AI 将自动识别图谱数据，
智能区分 **还原(R)** 和 **非还原(NR)** 模式，并计算主峰纯度及碎片比例，最后生成 Excel 汇总表。
""")

with st.expander("⚙️ 高级设置 (可选)"):
    api_key_input = st.text_input("DeepSeek API Key (已内置默认 Key)", value=DEFAULT_API_KEY, type="password")

# 文件上传组件
uploaded_file = st.file_uploader("📂 请拖拽或点击上传 PDF 报告文件", type="pdf")

if uploaded_file is not None:
    if st.button("🚀 一键开始提取", type="primary"):
        # 进度指示器
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.info("正在读取 PDF 文件，请稍候...")
        
        try:
            with pdfplumber.open(uploaded_file) as pdf:
                pages = pdf.pages
                total_pages = len(pages)
                status_text.info(f"成功读取 PDF，共 {total_pages} 页。正在提取文本并发送给大模型处理...")
                
                client = OpenAI(api_key=api_key_input, base_url="https://api.deepseek.com")
                
                # 提取纯文本
                texts = [(i+1, p.extract_text()) for i, p in enumerate(pages) if p.extract_text()]
                
                parsed_data = []
                completed = 0
                
                # 多线程并发请求大模型
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {executor.submit(parse_page_with_llm, client, page_num, text): page_num for page_num, text in texts}
                    for future in concurrent.futures.as_completed(futures):
                        page_num, data = future.result()
                        if data and 'Peaks' in data and len(data['Peaks']) > 0:
                            parsed_data.append((page_num, data))
                        completed += 1
                        # 更新进度条
                        progress_val = int((completed / len(texts)) * 100)
                        progress_bar.progress(progress_val)
                        status_text.info(f"🤖 AI 解析进度: {completed} / {len(texts)} 页")
                        
            status_text.info(f"✅ 大模型解析完毕，成功提取到 {len(parsed_data)} 个样品的数据。正在执行专业计算...")
            
            # 按页码排序，保证输出顺序与 PDF 一致
            parsed_data.sort(key=lambda x: x[0])
            all_results = []
            
            for page_num, data in parsed_data:
                current_sample = data.get('Sample Name', 'Unknown')
                current_vial = data.get('Vial', 'Unknown')
                peaks = data.get('Peaks', [])
                
                if not peaks:
                    continue
                    
                peaks_df = pd.DataFrame(peaks)
                peaks_df['Purity'] = pd.to_numeric(peaks_df['Purity'], errors='coerce')
                peaks_df['Migration Time'] = pd.to_numeric(peaks_df['Migration Time'], errors='coerce')
                if 'Area' in peaks_df.columns:
                    peaks_df['Area'] = pd.to_numeric(peaks_df['Area'], errors='coerce')
                else:
                    peaks_df['Area'] = 0.0
                
                peaks_df = peaks_df.dropna(subset=['Purity', 'Migration Time'])
                
                # 强力清洗：剔除大模型提取错误的脏数据（真正的纯度不可能大于100%）
                peaks_df = peaks_df[peaks_df['Purity'] <= 100.0]
                
                if peaks_df.empty:
                    continue
                    
                # 严谨的正则判断还原(R)和非还原(NR)
                sample_upper = str(current_sample).upper()
                if re.search(r'\bNR\b|-NR\b', sample_upper):
                    is_reduced = False
                elif re.search(r'\bR\b|-R\b', sample_upper):
                    is_reduced = True
                else:
                    is_reduced = False  # 兜底默认为 NR
                    
                result_row = {
                    'Sample Name': current_sample,
                    'Vial': current_vial
                }
                
                if not is_reduced:
                    # 非还原(NR)逻辑
                    max_purity = peaks_df['Purity'].max()
                    
                    # 核心重构：精准定位“需要汇报的主峰(IgG)”
                    # 按照领导指示：主峰通常是最后的那个峰（通常在 28s 之后）
                    late_peaks = peaks_df[peaks_df['Migration Time'] >= 28.0]
                    
                    mp_area = 0.0 # 记录真正主峰(IgG)的面积
                    if not late_peaks.empty and late_peaks['Purity'].max() >= 0.2:
                        # 形态1：存在真实的晚出峰IgG（即使它降解得很严重，只要纯度>0.2%，它就是我们要找的目标）
                        mp_idx = late_peaks['Purity'].idxmax()
                        mp_row = peaks_df.loc[mp_idx]
                        mp_time = mp_row['Migration Time']
                        mp_purity = mp_row['Purity']
                        mp_area = float(mp_row['Area'])
                        # Fragments 为该最终主峰之前的所有峰（主峰后面的碎片峰坚决不计入）
                        fragments = peaks_df[peaks_df['Migration Time'] < mp_time]['Purity'].sum()
                    else:
                        # 形态2：完全没有晚出峰，属于早出峰多主峰形态 (如 20s 左右)
                        candidates = peaks_df[peaks_df['Purity'] > max_purity * 0.2].sort_values('Migration Time')
                        if not candidates.empty:
                            mp_purity = candidates['Purity'].sum()
                            mp_area = float(candidates['Area'].sum())
                            first_mp_time = candidates.iloc[0]['Migration Time']
                            # Fragments 为第一个主峰之前的所有碎峰
                            fragments = peaks_df[peaks_df['Migration Time'] < first_mp_time]['Purity'].sum()
                        else:
                            # 兜底逻辑
                            mp_idx = peaks_df['Purity'].idxmax()
                            mp_time = peaks_df.loc[mp_idx, 'Migration Time']
                            mp_purity = peaks_df.loc[mp_idx, 'Purity']
                            mp_area = float(peaks_df.loc[mp_idx, 'Area'])
                            fragments = peaks_df[peaks_df['Migration Time'] < mp_time]['Purity'].sum()
                    
                    # 浓度过滤：真正的汇报主峰 (IgG) 的 Area 不超过 415
                    if pd.isna(mp_area) or mp_area <= 415.0:
                        result_row['Fragments'] = '结果见图谱，供参考'
                        result_row['NR-MP/IgG'] = '结果见图谱，供参考'
                        all_results.append(result_row)
                        continue
                        
                    result_row['Fragments'] = round_half_up_1(fragments)
                    result_row['NR-MP/IgG'] = round_half_up_1(mp_purity)
                else:
                    # 还原(R)逻辑：处理 LC/HC 类型 和 特殊 R-MP 类型
                    # 浓度过滤标志：除第一行（系统峰）外，所有峰的 Area 最大值不超过 415
                    is_r_low_concentration = False
                    if len(peaks_df) > 1:
                        max_area_excluding_first = peaks_df.iloc[1:]['Area'].max()
                        if pd.isna(max_area_excluding_first) or max_area_excluding_first <= 415:
                            is_r_low_concentration = True
                    else:
                        # 如果只有一个峰（连主峰都没有，只有系统峰），也视为浓度太低
                        is_r_low_concentration = True

                    if is_r_low_concentration:
                        result_row['LC+HC'] = '结果见图谱，供参考'
                        result_row['NGHC'] = '结果见图谱，供参考'
                        result_row['R-MP'] = '结果见图谱，供参考'
                        all_results.append(result_row)
                        continue

                    # 恢复拓扑骨架的准入门槛到 >5.0%，保证最大间隙算法绝对稳定 (不受微小噪音干扰破坏形态)
                    candidates = peaks_df[peaks_df['Purity'] > 5.0].sort_values('Migration Time')
                    
                    if not candidates.empty:
                        if len(candidates) >= 2:
                            # 核心算法：最大时间间隙聚类 (寻找拓扑断层)
                            max_gap = 0
                            split_idx = 1
                            for i in range(1, len(candidates)):
                                gap = candidates.iloc[i]['Migration Time'] - candidates.iloc[i-1]['Migration Time']
                                if gap > max_gap:
                                    max_gap = gap
                                    split_idx = i
                                    
                            # 动态形态判定：如果最大的断层间隙大于 3.0s，说明是明显的 LC 和 HC 分离形态
                            # 如果小于等于 3.0s，说明所有主峰紧紧挤在一起(如21s~25s)，属于 R-MP 融合蛋白形态
                            if max_gap > 3.0:
                                # 以最大间隙为界，前面全是 LC，后面全是 HC
                                lc_group = candidates.iloc[:split_idx]
                                hc_group = candidates.iloc[split_idx:]
                                
                                # 目标1：完美加和。目标2：不破坏形态。
                                # 方案：形态由 >5.0% 的 candidates 决定。加和基数采用 >= 2.0% 的有效峰。
                                # 这完美包容了 3.88% 的 LC，同时排除了 0.14% 的噪音。
                                valid_sum_peaks = peaks_df[peaks_df['Purity'] >= 2.0]
                                lc_hc_total = valid_sum_peaks['Purity'].sum()
                                
                                # 启用多 NGHC 智能识别：严谨防假阳性策略
                                # 1. 动态相对时间窗：紧紧绑定在 HC 聚类的 **第一个** 峰前 0.2 ~ 1.2 秒
                                first_hc_time = hc_group.iloc[0]['Migration Time']
                                nghc_candidates = peaks_df[
                                    (peaks_df['Migration Time'] >= first_hc_time - 1.2) & 
                                    (peaks_df['Migration Time'] <= first_hc_time - 0.2)
                                ]
                                
                                # 2. 动态纯度阈值：对这批真实样本，NGHC 可低至 0.1% 左右
                                # 强制规则：对于名称中包含 'REP' 的样品，跳过纯度下限阈值，只要在时间窗内就算 NGHC
                                if 'REP' in sample_upper:
                                    valid_nghc = nghc_candidates[nghc_candidates['Purity'] <= 5.0]
                                else:
                                    valid_nghc = nghc_candidates[
                                        (nghc_candidates['Purity'] >= 0.1) & 
                                        (nghc_candidates['Purity'] <= 5.0)
                                    ]
                                
                                nghc_purity = 0.0
                                if not valid_nghc.empty:
                                    nghc_purity = valid_nghc['Purity'].sum()
                                    
                                result_row['NGHC'] = round_half_up_1(nghc_purity)
                                
                                # LC+HC 等于有效峰总和扣除掉那些被判定为 NGHC 且被算入总和的峰
                                for _, row in valid_nghc.iterrows():
                                    if row['Purity'] >= 2.0: 
                                        lc_hc_total -= row['Purity']
                                        
                                result_row['LC+HC'] = round_half_up_1(lc_hc_total)
                            else:
                                # 没有明显的 LC/HC 断层，属于连续的 R-MP 多峰形态
                                r_mp_purity = candidates['Purity'].sum()
                                result_row['R-MP'] = round_half_up_1(r_mp_purity)
                        else:
                            # 只有一个主峰的情况的兜底逻辑
                            first_major_time = candidates.iloc[0]['Migration Time']
                            if first_major_time >= 22.0:
                                result_row['R-MP'] = round_half_up_1(candidates.iloc[0]['Purity'])
                            else:
                                # 同样放宽加和基数
                                valid_sum_peaks = peaks_df[peaks_df['Purity'] >= 2.0]
                                result_row['LC+HC'] = round_half_up_1(valid_sum_peaks['Purity'].sum())
                                result_row['NGHC'] = 0.0
                        
                all_results.append(result_row)
                
            if not all_results:
                st.error("未能计算出任何有效结果，请检查 PDF 格式。")
            else:
                df_all = pd.DataFrame(all_results)
                formatted_df_all = df_all.copy()
                for col in formatted_df_all.columns:
                    if col not in ['Sample Name', 'Vial']:
                        formatted_df_all[col] = formatted_df_all[col].apply(format_result_value)
                
                # 将数据写入内存中的 Excel
                output_buffer = io.BytesIO()
                with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
                    has_data = False
                    if 'Fragments' in formatted_df_all.columns:
                        df_nr = formatted_df_all[['Sample Name', 'Vial', 'Fragments', 'NR-MP/IgG']].dropna(subset=['Fragments', 'NR-MP/IgG'])
                        if not df_nr.empty:
                            df_nr.to_excel(writer, sheet_name='Non-Reduced (NR)', index=False)
                            has_data = True
                    
                    if 'LC+HC' in formatted_df_all.columns or 'R-MP' in formatted_df_all.columns:
                        cols_r = ['Sample Name', 'Vial']
                        if 'LC+HC' in formatted_df_all.columns: cols_r.append('LC+HC')
                        if 'NGHC' in formatted_df_all.columns: cols_r.append('NGHC')
                        if 'R-MP' in formatted_df_all.columns: cols_r.append('R-MP')
                        
                        cols_r = [c for c in cols_r if c in formatted_df_all.columns]
                        df_r = formatted_df_all[cols_r].dropna(subset=[c for c in cols_r if c not in ['Sample Name', 'Vial']], how='all')
                        if not df_r.empty:
                            df_r.to_excel(writer, sheet_name='Reduced (R)', index=False)
                            has_data = True
                            
                if has_data:
                    st.success("🎉 数据处理完成！请点击下方按钮下载 Excel 报表。")
                    st.balloons()
                    
                    # 提供下载按钮
                    st.download_button(
                        label="📥 下载 Excel 汇总表",
                        data=output_buffer.getvalue(),
                        file_name=f"Result_{uploaded_file.name.replace('.pdf', '')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                    
                    # 页面预览
                    st.markdown("### 📊 数据预览 (前 5 行)")
                    st.dataframe(formatted_df_all.head())
                else:
                    st.warning("没有提取到有效的 R 或 NR 数据。")
                    
        except Exception as e:
            st.error(f"处理过程中发生错误: {str(e)}")
