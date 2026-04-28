# wx-content-mesh-python

Python-only 架构源码：把 wxAiPost 适合借鉴的「后台/发布链路」拆出来，再补一个 WeMD-like 的微信排版层。

运维约束和账号能力边界见 [OPS.md](C:\Users\11614\Desktop\wx_content_mesh_python\wx_content_mesh_python\OPS.md)。

## 定位

- 不照搬 wxAiPost 的 Go + Vue + MySQL。
- 保留它值得借鉴的部分：账号表、token 缓存、封面素材上传、草稿创建、发布提交、发布记录、后台 API 雏形。
- 排版层单独实现：Markdown -> 微信兼容 inline HTML -> 本地手机宽度预览 -> 草稿。
- 小红书采用安全导出包，不做绕过登录/风控的自动化。

## 目录

```text
wx_content_mesh/
├── app.py                         # FastAPI 后台雏形，自带 Swagger UI
├── cli.py                         # 命令行入口
├── config.py                      # 环境配置
├── db.py                          # SQLAlchemy DB 初始化
├── models.py                      # 账号/token/素材/文章/发布任务表
├── schemas.py                     # API schema
├── scheduler.py                   # 定时提交/轮询雏形
└── services/
    ├── renderer.py                # WeMD-like Markdown -> inline HTML
    ├── wechat_client.py           # 微信 token/素材/草稿/预览/发布 API
    ├── image_service.py           # 图片下载、去重、hash、素材记录
    ├── publisher.py               # 渲染 -> 上传图片 -> 草稿 -> 预览 -> 发布
    ├── xhs_exporter.py            # 小红书笔记导出
    ├── creative_pipeline.py       # 研究员 -> 作家 -> 审核员 -> 设计师
    ├── quality_gate.py            # 发布前质量/风险检查
    └── llm.py                     # OpenAI-compatible LLM 客户端
```

## 发布链路

```text
Article Markdown
  -> render_article()
      Markdown -> inline HTML
      local preview HTML
  -> create_wechat_draft()
      upload inline images with media/uploadimg
      upload cover with material/add_material
      draft/add returns media_id
  -> send_preview()
      message/mass/preview sends to openid/wxname
  -> submit_freepublish()
      freepublish/submit returns publish_id
  -> poll_publish_status()
      freepublish/get returns status/article_id
      freepublish/getarticle tries to hydrate article URL
```

注意：「预览链接」在这里拆成两类：

1. `local_preview_url`：你后台本地的 HTML 预览链接，适合排版审稿。
2. 微信手机预览：调用 `message/mass/preview` 发送到指定用户。微信接口不会为草稿直接返回一个公开预览 URL。

## 个人号边界

当前仓库已经验证过一个典型个人主体公众号的能力边界：

- 个人主体账号不等于可开通完整 `微信认证`
- 个人号可以启用 `AppSecret`、配置 IP 白名单、获取 `access_token`
- 个人号可以创建草稿 `draft/add`
- 个人号当前没有 `message/mass/preview` 权限，实测返回 `48001 api unauthorized`
- 对 `freepublish/submit` 这类自动发布能力，不应默认认为个人未认证账号可用

因此，当前项目默认按“草稿箱模式”运行：

- 开 `local preview`
- 开 `draft/add`
- 关 `preview`
- 关 `freepublish/submit`

只有在确认账号能力足够后，才手动打开运行开关：

```bash
WCM_ALLOW_WECHAT_PREVIEW=true
WCM_ALLOW_WECHAT_PUBLISH=true
```

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.env .env
python -m wx_content_mesh.cli init
```

Windows 本地推荐用 uv：

```powershell
uv venv .venv
uv pip install --python .\.venv\Scripts\python.exe -r requirements-dev.txt
.\.venv\Scripts\python.exe -m wx_content_mesh.cli init
```

启动后台：

```bash
uvicorn wx_content_mesh.app:app --reload
```

打开：

```text
http://127.0.0.1:8000/docs
```

本地渲染演示：

```bash
python examples/demo_local.py
```

## 配置公众号账号

推荐把 secret 放到环境变量，再让账号表引用变量名：

```bash
export WX_ACCOUNT_MAIN_SECRET="你的 AppSecret"
python -m wx_content_mesh.cli add-account \
  --name main \
  --appid wx_xxx \
  --secret-env-name WX_ACCOUNT_MAIN_SECRET \
  --account-type service \
  --certified \
  --author "你的作者名" \
  --default-cover-media-id "已上传封面media_id"
```

也可以本地测试时直接传 `--secret`，但生产不建议。

默认安全开关：

```bash
WCM_ALLOW_WECHAT_PREVIEW=false
WCM_ALLOW_WECHAT_PUBLISH=false
```

## 创建文章并预览

```bash
python -m wx_content_mesh.cli create-article \
  --account-id 1 \
  --title "wxAiPost 应该怎么借鉴，而不是照搬" \
  --markdown examples/sample_article.md \
  --cover ./cover.jpg \
  --theme wemd_card

python -m wx_content_mesh.cli render 1
```

查看文章、质量检查和发布任务：

```bash
python -m wx_content_mesh.cli list-articles
python -m wx_content_mesh.cli inspect 1
python -m wx_content_mesh.cli jobs --article-id 1
```

## 创建微信草稿

```bash
python -m wx_content_mesh.cli draft 1
```

## 发送手机预览

```bash
python -m wx_content_mesh.cli preview 1 --openid USER_OPENID
# 或者，在账号允许的情况下：
python -m wx_content_mesh.cli preview 1 --wxname SOME_WECHAT_ID
```

注意：不是所有公众号账号都具备 `message/mass/preview` 权限。当前测试用个人主体账号已验证：

- `draft/add` 可用
- `message/mass/preview` 返回 `48001 api unauthorized`
- `freepublish/submit` 默认关闭，不对个人未认证号做自动发布假设

所以当前默认工作流应当是：

- 本地预览
- 推送草稿箱
- 在公众号后台人工检查并手动发布

## 提交发布并轮询

```bash
python -m wx_content_mesh.cli publish 1
python -m wx_content_mesh.cli poll 1
```

## 小红书导出

```bash
python -m wx_content_mesh.cli xhs-export 1 --tags 公众号排版 内容自动化 Python
```

## 最优解建议

- wxAiPost：借后台表结构和发布链路，不借排版。
- WeMD：借排版理念、本地优先、主题、深色模式预览理念；Python 侧用 inline renderer 复刻关键能力。
- wechat-publisher / wechat-official-publisher：借 token、多账号、图片上传、草稿创建、错误处理。
- xiaohu-wechat-format：借 Python 主题库、inline style、图片上传到草稿箱这条线。
- 最终系统：Python FastAPI + SQLAlchemy + renderer + publisher + scheduler。

## 生产化待补

1. raw_secret 加密，例如 KMS/Fernet/Vault。
2. 图片格式压缩与微信尺寸限制自动修复。
3. Celery/RQ 替换内存 APScheduler。
4. 更完整的素材库、语义检索和选题系统。
5. 更完整的前端后台；当前可先用 FastAPI Swagger UI。
6. 如果要做全自动手机预览/发布，先确认账号主体和平台权限，不要默认个人主体账号可开通。

## 本地验证

```bash
python examples/demo_local.py
pytest -q
```

当前测试覆盖：

- Markdown -> 微信 inline HTML、callout、目录、外链脚注。
- 图片素材建档与同账号去重。
- freepublish 状态轮询与正式文章 URL 回填。
