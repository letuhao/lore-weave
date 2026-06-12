"""One-shot script: add mining section to all 4 knowledge.json locale files."""
import json

BASE = "d:/Works/source/lore-weave/frontend/src/i18n/locales"

MINING = {
    "en": {
        "sections": {
            "configQuality": {
                "title": "Config Quality",
                "description": "Success rate by genre and configuration. Populated after 2+ extraction runs sharing the same config hash.",
                "empty": "No data yet — needs 2+ extraction runs with the same config hash per genre.",
                "exploration": "Exploration sample (random tail)"
            },
            "modelMatrix": {
                "title": "Model Matrix",
                "description": "Weighted outcome score by model and task scope. succeeded=1.0 · skipped=0.3 · failed=0.0.",
                "empty": "No data yet — needs 2+ extraction runs with the same model and scope."
            },
            "defaultDrift": {
                "title": "Config Drift",
                "description": "Which extraction parameters deviate from defaults, and whether projects converge on the same value.",
                "empty": "No parameter adjustments recorded yet."
            },
            "outcomeRecompute": {
                "title": "Outcome Recompute",
                "description": "Extraction runs re-evaluated after applying post-run user corrections.",
                "empty": "No correction data yet. Outcome recompute activates once corrections link back to an extraction run."
            }
        },
        "columns": {
            "genre": "Genre",
            "configHash": "Config",
            "runs": "Runs",
            "successRate": "Success rate",
            "avgEntities": "Avg entities",
            "model": "Model",
            "scope": "Scope",
            "filter": "Filter",
            "weightedOutcome": "Score",
            "target": "Parameter",
            "affectedProjects": "Projects",
            "driftPattern": "Pattern",
            "runsWithOutcome": "Runs w/ outcome",
            "runId": "Run",
            "outcome": "Outcome",
            "recomputed": "Recomputed",
            "corrections": "Corrections"
        },
        "driftPattern": {
            "convergent": "Convergent",
            "divergent": "Divergent"
        },
        "totalRuns": "{{count}} runs total"
    },
    "vi": {
        "sections": {
            "configQuality": {
                "title": "Chất lượng cấu hình",
                "description": "Tỷ lệ thành công theo thể loại và cấu hình. Có dữ liệu sau 2+ lần trích xuất dùng cùng config hash.",
                "empty": "Chưa có dữ liệu — cần 2+ lần trích xuất với cùng config hash trên mỗi thể loại.",
                "exploration": "Mẫu khám phá (ngẫu nhiên)"
            },
            "modelMatrix": {
                "title": "Ma trận mô hình",
                "description": "Điểm kết quả theo mô hình và phạm vi tác vụ. succeeded=1.0 · skipped=0.3 · failed=0.0.",
                "empty": "Chưa có dữ liệu — cần 2+ lần trích xuất với cùng mô hình và phạm vi."
            },
            "defaultDrift": {
                "title": "Độ lệch cấu hình",
                "description": "Tham số nào khác so với mặc định, và liệu các dự án có hội tụ về cùng giá trị không.",
                "empty": "Chưa ghi nhận điều chỉnh tham số nào."
            },
            "outcomeRecompute": {
                "title": "Tái tính kết quả",
                "description": "Các lần trích xuất được đánh giá lại sau khi áp dụng hiệu chỉnh của người dùng.",
                "empty": "Chưa có dữ liệu hiệu chỉnh. Tính năng này kích hoạt khi hiệu chỉnh được liên kết với lần trích xuất."
            }
        },
        "columns": {
            "genre": "Thể loại",
            "configHash": "Cấu hình",
            "runs": "Lượt",
            "successRate": "Tỷ lệ thành công",
            "avgEntities": "TB thực thể",
            "model": "Mô hình",
            "scope": "Phạm vi",
            "filter": "Bộ lọc",
            "weightedOutcome": "Điểm",
            "target": "Tham số",
            "affectedProjects": "Dự án",
            "driftPattern": "Kiểu lệch",
            "runsWithOutcome": "Lượt có kết quả",
            "runId": "Lượt",
            "outcome": "Kết quả",
            "recomputed": "Tái tính",
            "corrections": "Hiệu chỉnh"
        },
        "driftPattern": {
            "convergent": "Hội tụ",
            "divergent": "Phân kỳ"
        },
        "totalRuns": "{{count}} lượt tổng cộng"
    },
    "ja": {
        "sections": {
            "configQuality": {
                "title": "設定品質",
                "description": "ジャンルと設定別の成功率。同じ設定ハッシュの抽出を 2 回以上実行後に表示されます。",
                "empty": "データなし — ジャンルごとに同じ設定ハッシュで 2 回以上の抽出が必要です。",
                "exploration": "探索サンプル（ランダム末尾）"
            },
            "modelMatrix": {
                "title": "モデルマトリクス",
                "description": "モデルとタスクスコープ別の重み付き結果スコア。succeeded=1.0 · skipped=0.3 · failed=0.0。",
                "empty": "データなし — 同じモデルとスコープで 2 回以上の抽出が必要です。"
            },
            "defaultDrift": {
                "title": "設定ドリフト",
                "description": "デフォルトと異なる抽出パラメータと、プロジェクト間で同じ値に収束しているかどうか。",
                "empty": "パラメータ調整の記録がまだありません。"
            },
            "outcomeRecompute": {
                "title": "結果再計算",
                "description": "ユーザー修正を適用後に再評価された抽出実行。",
                "empty": "修正データがまだありません。修正が抽出実行に結び付いた時点で機能が有効になります。"
            }
        },
        "columns": {
            "genre": "ジャンル",
            "configHash": "設定",
            "runs": "実行数",
            "successRate": "成功率",
            "avgEntities": "平均エンティティ",
            "model": "モデル",
            "scope": "スコープ",
            "filter": "フィルタ",
            "weightedOutcome": "スコア",
            "target": "パラメータ",
            "affectedProjects": "プロジェクト",
            "driftPattern": "パターン",
            "runsWithOutcome": "結果あり実行",
            "runId": "実行",
            "outcome": "結果",
            "recomputed": "再計算",
            "corrections": "修正"
        },
        "driftPattern": {
            "convergent": "収束",
            "divergent": "分岐"
        },
        "totalRuns": "合計 {{count}} 件"
    },
    "zh-TW": {
        "sections": {
            "configQuality": {
                "title": "配置品質",
                "description": "依類型和配置的成功率。同一配置雜湊執行 2 次以上後顯示資料。",
                "empty": "尚無資料 — 每個類型需要 2 次以上使用相同配置雜湊的擷取。",
                "exploration": "探索樣本（隨機末段）"
            },
            "modelMatrix": {
                "title": "模型矩陣",
                "description": "依模型和任務範圍的加權結果分數。succeeded=1.0 · skipped=0.3 · failed=0.0。",
                "empty": "尚無資料 — 需要 2 次以上使用相同模型和範圍的擷取。"
            },
            "defaultDrift": {
                "title": "配置漂移",
                "description": "哪些擷取參數偏離預設値，以及各專案是否趨向相同値。",
                "empty": "尚未記錄任何參數調整。"
            },
            "outcomeRecompute": {
                "title": "結果重算",
                "description": "套用使用者校正後重新評估的擷取執行。",
                "empty": "尚無校正資料。當校正連結到擷取執行時，此功能將啟用。"
            }
        },
        "columns": {
            "genre": "類型",
            "configHash": "配置",
            "runs": "次數",
            "successRate": "成功率",
            "avgEntities": "平均實體",
            "model": "模型",
            "scope": "範圍",
            "filter": "過濾器",
            "weightedOutcome": "分數",
            "target": "參數",
            "affectedProjects": "專案",
            "driftPattern": "模式",
            "runsWithOutcome": "有結果的執行",
            "runId": "執行",
            "outcome": "結果",
            "recomputed": "重算",
            "corrections": "校正"
        },
        "driftPattern": {
            "convergent": "收斂",
            "divergent": "發散"
        },
        "totalRuns": "共 {{count}} 次執行"
    }
}

for lang, m in MINING.items():
    path = f"{BASE}/{lang}/knowledge.json"
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    d["mining"] = m
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f"{lang}: OK, keys = {list(d.keys())}")

print("Done.")
