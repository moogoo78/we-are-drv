"""課後問卷題目，依「防災士課後問卷調查」公版格式（題號五～二十五）。"""

COURSES = [
    "我國近年災害經驗及災害特性",
    "防災士職責與任務、我國災防體系與運作",
    "資訊掌握、運用與社區防災計畫",
    "社區防災工作推動與運作",
    "個人與居家防護措施",
    "個人與居家防護措施(含情境練習)",
    "社區避難收容場所開設與運作",
    "防災計畫實作與驗證",
    "基礎急救訓練(含實作及測驗)",
]

RATING_ASPECTS = ["課程實用性", "課程難易度", "講師表達能力", "講師互動能力", "講師專業度"]

DISTRICTS = ["仁愛區", "信義區", "中正區", "中山區", "安樂區", "暖暖區", "七堵區", "皆可"]

WILLING = ["願意", "不願意"]

QUESTIONS = [
    {"id": "occupation", "label": "五、職業", "type": "single",
     "options": ["軍/警/公/教", "國營企業", "工商業", "服務業", "醫療照護", "學生", "退休／待業", "其他"]},
    {"id": "reason", "label": "六、參訓緣由", "type": "single",
     "options": ["個人興趣", "公司/機構要求", "社區／里辦公處推薦", "其他"]},
    {"id": "advanced", "label": "七、未來您是否願意自費參與防災士進階課程教育訓練（例如避難收容、輕搜救、通訊設備、緊急救護等）？",
     "type": "single", "options": WILLING},
    {"id": "data_consent", "label": "八、您是否同意公務機關或委託機關因防救災業務需求，蒐集、使用或運用您的個人資料？",
     "type": "single", "options": ["同意", "不同意"]},
    {"id": "recruit_guide", "label": "九、災害發生時，是否願意收到志工召募通知，協助【協助引導與疏散】？", "type": "single", "options": WILLING},
    {"id": "recruit_supply", "label": "九、災害發生時，是否願意收到志工召募通知，協助【物資發放】？", "type": "single", "options": WILLING},
    {"id": "recruit_shelter", "label": "九、災害發生時，是否願意收到志工召募通知，協助【收容場所開設】？", "type": "single", "options": WILLING},
    {"id": "recruit_all", "label": "九、災害發生時，是否願意收到志工召募通知，協助【皆可】？", "type": "single", "options": WILLING},
    {"id": "center", "label": "十、災害發生時，您是否願意加入「防災協作中心」協助支援？", "type": "single",
     "options": ["願意", "視情況協助", "不願意"]},
    {"id": "teams", "label": "十一、您願意參與「防災協作中心」之任務編組？（可複選）", "type": "multi",
     "options": [
         "疏散撤離小組：協助高齡者、行動不便者及居民進行避難引導與撤離通報。",
         "避難收容小組：協助避難收容處所報到、環境維護、民眾關懷及秩序維持。",
         "物資發放小組：協助救援物資搬運、整理、發放及需求統計。",
     ]},
    {"id": "areas", "label": "十二、當發生災害時，您願意參與哪個行政區之防災工作？（可複選）", "type": "multi", "options": DISTRICTS},
    {"id": "skills", "label": "十三、請問您具備下列何種專業背景或專長？（可複選）", "type": "multi",
     "options": [
         "醫護或急救相關背景", "社工／心理關懷相關背景", "行政文書與資料整理能力",
         "物資管理或倉儲物流經驗", "無特殊專長，但願意接受任務指派",
     ]},
    {"id": "times", "label": "十四、災害發生時，您可協助投入之時段為何？（可複選）", "type": "multi",
     "options": ["平日白天", "平日晚間", "假日全天", "可配合臨時通知", "視災害情況而定"]},
]

# 十五～二十三：各課程滿意度（1～5 分），二十四：整體滿意度，二十五：其他建議
CHINESE_NUM = ["十五", "十六", "十七", "十八", "十九", "二十", "二十一", "二十二", "二十三"]
for i, course in enumerate(COURSES):
    for j, aspect in enumerate(RATING_ASPECTS):
        QUESTIONS.append({
            "id": f"c{i}_{j}",
            "label": f"{CHINESE_NUM[i]}、「{course}」課程滿意度 [{aspect}]",
            "type": "rating",
            "group": f"{CHINESE_NUM[i]}、「{course}」",
            "aspect": aspect,
        })
QUESTIONS.append({"id": "overall", "label": "二十四、您對於整體課程規劃辦理是否滿意？", "type": "rating",
                  "group": "二十四、整體課程規劃", "aspect": "課程整體規劃滿意度"})
QUESTIONS.append({"id": "suggestion", "label": "二十五、其他建議事項", "type": "text", "optional": True})


def validate(answers):
    """回傳錯誤訊息，或 None 表示通過。"""
    if not isinstance(answers, dict):
        return "問卷格式錯誤"
    for q in QUESTIONS:
        v = answers.get(q["id"])
        if q.get("optional") and (v is None or v == ""):
            continue
        if q["type"] == "single" and v not in q["options"]:
            return f"請回答：{q['label']}"
        if q["type"] == "multi":
            if not isinstance(v, list) or not v or any(x not in q["options"] for x in v):
                return f"請回答：{q['label']}"
        if q["type"] == "rating" and v not in (1, 2, 3, 4, 5):
            return f"請評分：{q['label']}"
        if q["type"] == "text" and not isinstance(v, str):
            return f"請回答：{q['label']}"
    return None
