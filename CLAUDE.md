# SHORT SCRIPT FACTORY — Claude Code Instructions

> **Mục tiêu**: Build nhà máy tạo kịch bản video ngắn tự động, kết nối với Video Factory & Doodle Factory.
> **Tech Stack**: Python orchestrator + Supabase + Vertex-Key LLM
> **Working Directory**: `/Users/rio/Active/TPE/short-script/`

## ⚠️ BẮT BUỘC — ĐỌC TRƯỚC KHI LÀM BẤT CỨ GÌ

### 1. Đọc Sổ Bàn Giao
```
Đọc file: .claude/handoff.md
```
Chứa: task hiện tại, acceptance criteria, quyết định đã chốt, kết quả phiên trước.

**Quy tắc:**
- Nếu có task → hỏi anh: "Em thấy task [tên] trong sổ bàn giao. Bắt đầu không?"
- Nếu không có task → hỏi anh cần gì
- KHÔNG thay đổi decisions đã chốt

### 2. Khi kết thúc session — BẮT BUỘC
```
→ CẬP NHẬT kết quả vào .claude/handoff.md:
  - Thêm entry mới ở ĐẦU mục "KẾT QUẢ PHIÊN"
  - Ghi: Status, files đã thay đổi, test results, đang dở gì
  - Đánh dấu Acceptance Criteria nào đã đạt
```

### 3. Spec Files
```
Đọc: .claude/spec/ khi CẦN:
  - script-formats.md — JSON schema cho slide_plan + doodle_script
  - voice-dna.md — Thông Phan voice rules (BẮT BUỘC đọc trước khi viết prompts)
  - forge-integration.md — Supabase tables & query patterns cho Forge Engine
```

---

## 🚨 ISOLATION — TUYỆT ĐỐI

```
/Users/rio/Active/TPE/
├── tpe-video-factory/     ← DỰ ÁN KHÁC (reference OK, KHÔNG SỬA)
├── doodle-factory/        ← DỰ ÁN KHÁC (reference OK, KHÔNG SỬA)
├── forge-engine/          ← DỰ ÁN KHÁC (reference OK, KHÔNG SỬA)
├── short-script/          ← DỰ ÁN NÀY
└── tpe-*                  ← KHÔNG LIÊN QUAN
```

1. KHÔNG đọc/sửa files ngoài `short-script/`
2. CÓ THỂ reference code từ `tpe-video-factory/orchestrator/` và `doodle-factory/orchestrator/` để học pattern
3. Venv riêng, .env riêng

---

## CRITICAL RULES

1. **KHÔNG dùng LangGraph** — Python thuần
2. **Logging**: `logging` module chuẩn, KHÔNG `print()` hay `rich`
3. **No hardcode secrets**: Tất cả qua `.env`
4. **Streaming LLM**: LUÔN dùng `stream=True` cho OpenAI SDK calls (tránh CloudFlare 524 timeout)
5. **JSON output**: LLM trả về JSON → parse cẩn thận, handle ```json``` code blocks
6. **Tests**: Mock ALL external APIs (LLM, Supabase, DibiVoice) — KHÔNG call API thật trong tests

## ENVIRONMENT

### Credentials (.env)
```
VERTEX_API_KEY=vai-bqJhQrgxPmFGnD6NfdJ0GS2BvwgKwwxMtUCM6FznOdV02F0P
VERTEX_BASE_URL=https://omega.vertex-key.com/v1
MODEL_WRITER=claude-sonnet-4-6
MODEL_QA=gemini-2.0-flash
SUPABASE_URL=https://bksqlgwotvpabksnynbo.supabase.co
SUPABASE_SERVICE_KEY=<cần lấy từ Supabase dashboard>
SUPABASE_ANON_KEY=<cần lấy từ Supabase dashboard>
```

### Setup
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

---

*File này load tự động. Đọc tiếp `.claude/handoff.md` để nắm task hiện tại.*
