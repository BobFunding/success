# 다른 AI가 사이트를 직접 보고 장면 표 초안을 쓰게 하기 (Playwright MCP)

튜토리얼 메이커의 [AI에게 맡기기]는 Claude 키가 있을 때 프로그램 안에서 돌아갑니다. 키 없이, 이미 쓰는 AI 도구
(Claude Code, Gemini CLI, Cursor 등)로 같은 일을 하려면 그 도구에 **Playwright MCP 서버**를 연결해 사이트를 직접 보게 하세요.

1. 연결 (Node.js 18 이상 필요)
   - Claude Code: `claude mcp add playwright -- npx @playwright/mcp@latest`
   - Gemini CLI: `~/.gemini/settings.json` 의 `mcpServers` 에 `"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}`
   - 그 밖의 도구: 각 도구의 MCP 설정에 같은 명령을 넣습니다.
2. 부탁하기: "`tutorials/시나리오_요청문.md` 규칙대로, 브라우저로 <<주소>> 에 들어가 <<무엇을 하는 방법>>을 직접 해 보고 장면 표를 써 줘.
   저장·등록·발송 버튼은 누르지 말고, 비밀번호는 나에게 물어봐."
3. 받은 `scenario.yaml` 을 `python tutorial.py check <파일>` 로 리허설 → 튜토리얼 메이커에서 열어 다듬고 만들기.

주의
- 그 AI 도구는 튜토리얼 메이커의 저장 차단을 거치지 않습니다. 저장·발송 버튼을 누르지 말라고 꼭 적고, 데모 계정으로 하세요.
- 비밀번호는 장면 표에 적지 말고 "@보관함" 으로 두세요(튜토리얼 메이커 확인 화면에서 한 번 넣으면 보관함에 저장).
