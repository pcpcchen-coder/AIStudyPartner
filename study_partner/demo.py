"""Hand-authored fixtures; these are never represented as model inference."""

from .schemas import Observation, TutorAnalysis

CASES = {
    "數學": (
        "24 ÷ 3 + 5 = ?",
        "3",
        "四則運算順序",
        ["算式裡有哪些不同的運算符號？", "先算除法，再把那個結果加上 5。"],
        "先除後加：24 ÷ 3 = 8，接著 8 + 5 = 13。答案是 13。",
        [
            ("18 ÷ 3 + 4 = ?", "10", "18 ÷ 3 = 6，6 + 4 = 10。"),
            ("20 − 12 ÷ 4 = ?", "17", "先算 12 ÷ 4 = 3，再算 20 − 3 = 17。"),
        ],
    ),
    "英文": (
        "Fill in the blank: She ___ to school every day. (go / goes)",
        "go",
        "現在簡單式與第三人稱單數",
        ["先找找這句話的主詞。", "主詞是 she，想想現在簡單式的動詞字尾。"],
        "She 是第三人稱單數，現在簡單式的 go 要變成 goes：She goes to school every day.",
        [("He ___ breakfast at seven. (eat / eats)", "eats", "He 是第三人稱單數，所以用 eats。")],
    ),
    "國語": (
        "請用『因為……所以……』寫一句話。",
        "因為下雨，所以我帶傘。",
        "因果關係",
        ["前半句說原因，後半句說結果。", "試著檢查原因和結果是否真的有關係。"],
        "這句話有合理的因果關係：下雨是原因，帶傘是結果。造句可以有多種正確答案。",
        [
            (
                "用『雖然……但是……』寫一句話。",
                "雖然下雨，但是我們仍然準時到校。",
                "這是參考答案。前後兩句要形成轉折，不是唯一寫法。",
            )
        ],
    ),
    "自然": (
        "水在一般大氣壓下加熱到約幾度會沸騰？請寫攝氏溫度。",
        "50°C",
        "水的沸點",
        ["留意題目限定的壓力條件。", "想想溫度計上，水的凝固與沸騰各是什麼溫度。"],
        "一般大氣壓下，純水的沸點約為 100°C。壓力不同時，沸點也會改變。",
        [("高山上的大氣壓較低，水的沸點通常較高還是較低？", "較低", "壓力下降時水較容易沸騰。")],
    ),
    "社會": (
        "地圖上的比例尺 1:10000，圖上 1 公分代表實際幾公尺？",
        "10000 公尺",
        "比例尺與單位",
        ["比例尺兩邊使用相同單位。", "先得到實際的公分數，再把公分換成公尺。"],
        "圖上 1 公分代表實際 10000 公分；100 公分 = 1 公尺，所以實際是 100 公尺。",
        [
            (
                "比例尺 1:5000，圖上 2 公分代表實際幾公尺？",
                "100 公尺",
                "2 × 5000 = 10000 公分 = 100 公尺。",
            )
        ],
    ),
    "其他": (
        "請列出你準備報告時會先做的兩件事。",
        "找資料、整理重點",
        "規劃與表達",
        ["先想想報告要讓聽眾知道什麼。", "你的步驟是否有順序？資料來源能否確認？"],
        "找資料、整理重點是合理的開始。也可以先設定主題與問題，再蒐集可靠來源。這是開放題。",
        [
            (
                "替一份介紹家鄉的報告列三個小標題。",
                "位置、特色、生活",
                "這只是範例，可依報告目的安排。",
            )
        ],
    ),
}


def demo(subject):
    question, answer, concept, hints, explanation, exercises = CASES[subject]
    observation = Observation(
        question=question,
        student_answer=answer,
        subject=subject,
        concept=concept,
        confidence=1,
        quality="clear",
        clarification="",
    )
    analysis = TutorAnalysis(
        verdict="uncertain" if subject in ("國語", "其他") else "needs_work",
        confidence=1,
        concept=concept,
        feedback="我們一起檢查這個觀念。",
        hints=hints,
        explanation=explanation,
        exercises=[{"question": q, "answer": a, "explanation": e} for q, a, e in exercises],
    )
    return observation, analysis
