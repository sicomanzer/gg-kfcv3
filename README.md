# 🇹🇭 Thai Value Investor (VI) Stock Screener

**โปรแกรมคัดกรองและวิเคราะห์หุ้นคุณค่า (VI Stock Screener)** เป็นเว็บแอปพลิเคชันที่พัฒนาด้วย Python และ Streamlit เพื่อช่วยให้นักลงทุนไทยค้นหาหุ้นคุณภาพดี ราคาเหมาะสม ตามหลักการ Value Investing (VI)

![App Screenshot](https://via.placeholder.com/800x400?text=Thai+VI+Stock+Screener+Dashboard)

## 🌟 ฟีเจอร์หลัก (Key Features)

1.  **📊 Dashboard & Screener**:
    *   คัดกรองหุ้น SET100 อัตโนมัติด้วย **VI Quality Score (10 คะแนน)** *[New!]*
    *   เพิ่มเกณฑ์คัดกรองเข้มข้น: **FCF > 0, PEG < 1.5, Liquidity, Gross Margin**
    *   แสดงหุ้นที่ Undervalued (ราคาต่ำกว่ามูลค่าที่แท้จริง)
    *   **Sector Heatmap**: แผนภาพความร้อนดูภาพรวมตลาดแยกตามอุตสาหกรรม

2.  **🔎 วิเคราะห์หุ้นเจาะลึก (Pro Analysis)**:
    *   ดูงบการเงินย้อนหลัง (รายได้, กำไร, EPS) ในรูปแบบกราฟ
    *   **Automated Valuation**: ประเมินมูลค่าเหมาะสมด้วย 3 วิธี (DDM, P/E, P/BV) พร้อมบอก Margin of Safety (MOS)
    *   **VI Price & Graham Number**: ราคาเหมาะสมแบบลูกผสม (Hybrid) และสูตรอมตะของ Benjamin Graham
    *   **Advanced Metrics**: เจาะลึกด้วย **Altman Z-Score** (ความเสี่ยงล้มละลาย), **SGR** (การเติบโตยั่งยืน), และ **FCF Yield** (กระแสเงินสดอิสระ)
    *   **Data Verification**: ตรวจสอบความถูกต้องของข้อมูลดิบ (Raw Data Inspector) พร้อมระบุเวลาล่าสุด *[New!]*
    *   **Checklist VI**: แบบประเมินคุณภาพหุ้น 8 ข้อ (เช่น ผู้นำตลาด, หนี้ต่ำ, ROE สูง)
    *   **📉 PE Band Matrix**: กราฟราคาเทียบกับค่า PE ย้อนหลัง 5 ปี พร้อมเส้น SD (+/- 1SD, 2SD) เพื่อดูโซนถูกแพงอย่างละเอียด

3.  **⚔️ เปรียบเทียบคู่แข่ง (Competitor Analysis)**:
    *   เทียบฟอร์มหุ้นรายตัวแบบ Head-to-Head
    *   เทียบอัตราส่วนทางการเงิน (ROE, NPM, D/E) และกราฟการเติบโต

4.  **🍰 Asset Allocation & Portfolio**:
    *   **แนะนำพอร์ตการลงทุน**: จัดสัดส่วนสินทรัพย์ (Asset Allocation) ตามความเสี่ยง
    *   **Portfolio Simulator**: จำลองจัดพอร์ตหุ้น 6 หมวดหมู่ (หุ้นไทย, ต่างประเทศ, ตราสารหนี้, REITs) พร้อมคำนวณปันผลคาดการณ์ *[New!]*
    *   **พอร์ตของฉัน (My Portfolio)**: บันทึกการซื้อขายจริง ติดตามกำไร/ขาดทุน (Realized/Unrealized)
    *   **⏳ DCA Backtester**: จำลองการออมหุ้นรายเดือนย้อนหลัง เพื่อดูพลังของดอกเบี้ยทบต้น

## 🛠️ เทคโนโลยีที่ใช้ (Tech Stack)

*   **Language**: Python 3.10+
*   **Framework**: Streamlit
*   **Data**: `yfinance` (Real-time & Historical Data from Yahoo Finance)
*   **Visualization**: Plotly Interactive Charts
*   **Analysis**: Pandas, NumPy

## 🚀 วิธีการติดตั้งและใช้งาน (Installation)

1.  **Clone โปรเจคนี้**:
    ```bash
    git clone https://github.com/sicomanzer/gg-kfcv3.git
    cd gg-kfcv3
    ```

2.  **ติดตั้ง Library ที่จำเป็น**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **รันโปรแกรม**:
    ```bash
    python -m streamlit run app.py
    ```

4.  **เปิดเว็บเบราว์เซอร์**:
    ไปที่ `http://localhost:8501`

## ⚠️ ข้อควรระวัง (Disclaimer)

*   ข้อมูลทั้งหมดดึงมาจากแหล่งข้อมูลสาธารณะ (Yahoo Finance) อาจมีความล่าช้าหรือคลาดเคลื่อนได้
*   การประเมินมูลค่า (Valuation) เป็นเพียงการประมาณการทางคณิตศาสตร์ ไม่ใช่คำแนะนำในการซื้อขายหลักทรัพย์
*   ผู้ใช้งานควรศึกษาข้อมูลเพิ่มเติมและตัดสินใจลงทุนด้วยตนเอง

---
*Developed for Educational Purposes based on VI Principles.*
