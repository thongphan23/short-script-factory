# Script Formats — JSON Schema cho Video Factory & Doodle Factory

> Mỗi target_factory cần output JSON format khác nhau.
> Script Writer PHẢI output đúng format tương ứng.

---

## Format A: Video Factory (Remotion) — `slide_plan.json`

**Target:** `tpe-video-factory` worker picks up từ Supabase `tpe_videos.script_json`
**Duration:** 60-120 giây
**Scenes:** 5-8

```json
{
  "title": "5 Cách Dùng AI Sai Mà 90% Dân Văn Phòng Đang Mắc",
  "totalDurationTarget": 60,
  "scenes": [
    {
      "id": 1,
      "type": "hook",
      "narration": "90% người dùng AI đang dùng sai, và họ không hề biết.",
      "durationSec": 8,
      "props": {},
      "visual_strategy": {
        "layout": "dramatic_number",
        "background": {
          "type": "gradient",
          "query": ""
        },
        "data_viz": {
          "type": "none",
          "data": []
        },
        "emphasis_element": "number_countup"
      }
    },
    {
      "id": 2,
      "type": "data_card",
      "narration": "...",
      "durationSec": 12,
      "props": {},
      "visual_strategy": {
        "layout": "card_list",
        "background": { "type": "gradient", "query": "" },
        "data_viz": {
          "type": "bar_horizontal",
          "data": [
            { "label": "Copy-paste prompt", "value": 70, "color": "blue" },
            { "label": "Có hệ thống prompt", "value": 15, "color": "gold" }
          ]
        },
        "emphasis_element": "typewriter"
      }
    }
  ]
}
```

### Visual Strategy Layouts (chọn theo nội dung):
- `dramatic_number` — Hook với con số gây sốc ("90%", "10x", "99%")
- `card_list` — Liệt kê 2-5 data points có label + value
- `pareto_chart` — Phân phối không đều (Pareto, Power Law)
- `bar_compare` — So sánh A vs B (horizontal bars)
- `quote_card` — Trích dẫn / insight sâu sắc
- `timeline_steps` — Quy trình 3-5 bước theo thứ tự
- `split_contrast` — Đối lập 2 góc nhìn (trước/sau, sai/đúng)
- `icon_grid` — Liệt kê 3-6 items với icon
- `brand_closing` — Kết thúc với CTA + brand identity

### Rules:
- Background: LUÔN `"type": "gradient"` (KHÔNG dùng stock_image)
- Scene đầu: luôn `dramatic_number`
- Scene cuối: luôn `brand_closing`
- Mỗi scene narration: ~15-20 từ/giây

---

## Format B: Doodle Factory (GPU) — `doodle_script.json`

**Target:** `doodle-factory` orchestrator/run.py hoặc doodle queue
**Duration:** 120-280 giây
**Scenes:** 15-35

```json
{
  "metadata": {
    "topic": "5 Cách Dùng AI Sai Mà 90% Dân Văn Phòng Đang Mắc",
    "channel": "ai",
    "target_audience": "Nhân viên văn phòng 22-35 tuổi muốn dùng AI hiệu quả",
    "estimated_duration_sec": 180,
    "created_at": "2026-04-07T20:00:00+07:00"
  },
  "scenes": [
    {
      "id": 1,
      "narration": "Anh em ơi, tui phát hiện ra 90% người dùng AI đang mắc sai lầm này nha.",
      "visual_prompt": "minimalist white line art on pure black background, simple doodle style, hand-drawn feel, clean white outlines, no shading, no gradient, no color, stick figure characters, person sitting at desk typing on laptop with confused expression",
      "motion_prompt": "stick figure typing frantically, question marks appearing above head",
      "duration_sec": 8
    }
  ],
  "full_narration": "Anh em ơi, tui phát hiện ra 90% người dùng AI đang mắc sai lầm này nha. ...",
  "hook_text": "90% người dùng AI đang mắc sai lầm này mà không hề biết."
}
```

### Doodle-Specific Rules:
- **visual_prompt** PHẢI bắt đầu với base prefix:
  ```
  minimalist white line art on pure black background, simple doodle style, hand-drawn feel, clean white outlines, no shading, no gradient, no color, stick figure characters,
  ```
- Tiếp theo: mô tả scene cụ thể (20-50 từ tiếng Anh)
- KHÔNG có text, nhãn, watermark trong ảnh
- **motion_prompt:** 5-15 từ tiếng Anh, present tense, action verbs
- **full_narration:** = ghép tất cả scene narrations bằng dấu cách
- **hook_text:** 1-2 câu hook hấp dẫn

### Structure:
1. **Hook** (5-8s): Câu hỏi provocative hoặc statement gây tò mò
2. **Problem** (30-60s): Phân tích vấn đề với ví dụ doodle
3. **Insight** (60-120s): Bài học chính, 2-4 key points, mỗi điểm 1-2 scenes
4. **Solution** (60-90s): Actionable steps, cụ thể, có thể làm ngay
5. **CTA** (10-20s): Gợi ý hành động cho viewer
