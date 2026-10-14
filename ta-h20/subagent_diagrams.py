"""subagent_diagrams.py <zh.html> <en.html>: insert/refresh the subagent flow + sequence diagrams section.

Mermaid renders natively in artifacts (<pre class="mermaid">). First run inserts the section before the
concurrency-scan section and renumbers the later headings; re-runs replace the section between markers.
"""
import re
import sys

FLOW = {
 "zh": """flowchart TB
  subgraph SB["Claude Code（沙箱）"]
    ROOT["主 agent<br/>x-claude-code-session-id = root"]
    SUBA["subagent a<br/>x-claude-code-agent-id = a"]
    SUBB["subagent b<br/>x-claude-code-agent-id = b"]
    ROOT -->|"Agent 工具（阻塞，可并行派多个）"| SUBA
    ROOT --> SUBB
  end
  subgraph GW["Gateway 适配器"]
    MW["ASGI 中间件<br/>请求头 → AgentIdentity(program, parent)"]
    TREE["session 的 program 树：root → a, b<br/>同一 program 串行，不同 program 并发"]
    REL["释放策略（客户端侧）<br/>① subagent 最后一轮 finish_reason=stop → 立即释放<br/>② 父的下一轮到来 → 释放仍空闲的子<br/>③ session 关闭 → 取消在飞 turn，子先根后释放"]
    MW --> TREE --> REL
  end
  subgraph CL["V1 client + TA server"]
    PC["program_id / parent_program_id<br/>→ thunderagent_session_id / parent<br/>路由键仍是轨迹 request_id：整棵树同一 frontend<br/>每个请求唯一 X-Request-Id"]
    HS["X-Dynamo-Session-ID<br/>X-Dynamo-Parent-Session-ID<br/>X-Dynamo-Session-Final<br/>awaiter 被取消 → ray.cancel → 断开 HTTP"]
    PC --> HS
  end
  subgraph DY["Dynamo · TA 插件"]
    TA1["program 带 parent_id · pin 到 worker<br/>容量核算 · pause / resume"]
    TA2["session-final 删整棵树<br/>客户端断连 → cancel_request 回滚，不留 zombie"]
  end
  subgraph EN["引擎 worker"]
    W0["worker 0 · TP4<br/>vLLM 或 SGLang"]
    W1["worker 1 · TP4<br/>vLLM 或 SGLang"]
  end
  ROOT & SUBA & SUBB -->|"OpenAI / Anthropic 兼容请求 + 身份头"| MW
  REL -->|"generate(program_id, parent_program_id)"| PC
  HS -->|"HTTP"| TA1
  TA1 -->|"同一 program 的每一轮 pin 同一卡，KV 留驻"| W0
  TA1 --> W1
  classDef changed fill:#eaf0fd,stroke:#2d6ae0,color:#16181d;
  classDef kept fill:#f3f4f7,stroke:#cbcfd9,color:#16181d;
  class MW,TREE,REL,PC,HS changed;
  class ROOT,SUBA,SUBB,TA1,TA2,W0,W1 kept;
""",
 "en": """flowchart TB
  subgraph SB["Claude Code (sandbox)"]
    ROOT["root agent<br/>x-claude-code-session-id = root"]
    SUBA["subagent a<br/>x-claude-code-agent-id = a"]
    SUBB["subagent b<br/>x-claude-code-agent-id = b"]
    ROOT -->|"Agent tool (blocking, several in parallel)"| SUBA
    ROOT --> SUBB
  end
  subgraph GW["Gateway adapter"]
    MW["ASGI middleware<br/>request headers → AgentIdentity(program, parent)"]
    TREE["program tree of the session: root → a, b<br/>serial within a program, concurrent across programs"]
    REL["release policy (client side)<br/>① subagent's last turn finish_reason=stop → release at once<br/>② parent's next turn → release its idle children<br/>③ session close → cancel in-flight turns, release children then root"]
    MW --> TREE --> REL
  end
  subgraph CL["V1 client + TA server"]
    PC["program_id / parent_program_id<br/>→ thunderagent_session_id / parent<br/>routing key stays the trajectory request_id: whole tree on one frontend<br/>unique X-Request-Id per request"]
    HS["X-Dynamo-Session-ID<br/>X-Dynamo-Parent-Session-ID<br/>X-Dynamo-Session-Final<br/>cancelled awaiter → ray.cancel → HTTP dropped"]
    PC --> HS
  end
  subgraph DY["Dynamo · TA plugin"]
    TA1["program with parent_id · pinned to a worker<br/>capacity model · pause / resume"]
    TA2["session-final removes the whole tree<br/>client disconnect → cancel_request rollback, no zombies"]
  end
  subgraph EN["engine workers"]
    W0["worker 0 · TP4<br/>vLLM or SGLang"]
    W1["worker 1 · TP4<br/>vLLM or SGLang"]
  end
  ROOT & SUBA & SUBB -->|"OpenAI / Anthropic-compatible request + identity headers"| MW
  REL -->|"generate(program_id, parent_program_id)"| PC
  HS -->|"HTTP"| TA1
  TA1 -->|"every turn of a program pinned to the same GPU, KV stays resident"| W0
  TA1 --> W1
  classDef changed fill:#eaf0fd,stroke:#2d6ae0,color:#16181d;
  classDef kept fill:#f3f4f7,stroke:#cbcfd9,color:#16181d;
  class MW,TREE,REL,PC,HS changed;
  class ROOT,SUBA,SUBB,TA1,TA2,W0,W1 kept;
""",
}

SEQ = {
 "zh": '''sequenceDiagram
  autonumber
  participant CC as Claude Code
  participant GW as Gateway 适配器
  participant CL as V1 client / TA server
  participant FE as Dynamo frontend + TA 插件
  participant EN as 引擎 worker
  CC->>GW: root 第 1 轮（session-id = root）
  GW->>CL: generate(program_id = root)
  CL->>FE: X-Dynamo-Session-ID: root
  FE->>EN: program root 建立，pin 到 worker 0
  EN-->>CC: 回复：调用 Agent 工具 ×2
  par 两个 subagent 并行
    CC->>GW: sub-a 第 1 轮（agent-id = a）
    GW->>CL: generate(program_id = a, parent = root)
    CL->>FE: Session-ID: a · Parent-Session-ID: root
    FE->>EN: program a 建立（parent = root），pin
  and
    CC->>GW: sub-b 第 1 轮（agent-id = b）
    GW->>CL: generate(program_id = b, parent = root)
    CL->>FE: Session-ID: b · Parent-Session-ID: root
    FE->>EN: program b 建立，pin
  end
  Note over GW: 同一 program 串行，不同 program 并发（原来会 409）
  loop sub-a / sub-b 各自的工具调用轮次
    CC->>GW: 第 n 轮
    FE->>EN: 仍 pin 同一卡，prefix 命中
  end
  CC->>GW: sub-a 最后一轮，finish_reason = stop
  GW->>CL: finalize_program(a)（规则 ①）
  CL->>FE: X-Dynamo-Session-Final: true（a）
  FE-->>FE: 删 program a，容量立即归还
  CC->>GW: root 恢复（Agent 工具已返回）
  GW->>CL: 先释放仍空闲的子 b（规则 ②），再 generate(root)
  FE->>EN: root 仍 pin worker 0
  alt 会话正常结束
    GW->>GW: finalize_session：等在飞 turn 自然结束（≤ 60 s）
  else 会话超时 / 中止（abort_session）
    GW->>CL: 取消在飞的 generate（asyncio cancel）
    CL->>CL: ray.cancel → server actor 断开 HTTP
    FE-->>FE: 请求回滚（cancel_request），不再占容量
  end
  GW->>CL: 释放树：子先，根 final（规则 ③）
  CL->>FE: X-Dynamo-Session-Final: true（root）
  FE-->>GW: 该 session 的 programs 归零
''',
 "en": '''sequenceDiagram
  autonumber
  participant CC as Claude Code
  participant GW as Gateway adapter
  participant CL as V1 client / TA server
  participant FE as Dynamo frontend + TA plugin
  participant EN as engine worker
  CC->>GW: root turn 1 (session-id = root)
  GW->>CL: generate(program_id = root)
  CL->>FE: X-Dynamo-Session-ID: root
  FE->>EN: program root created, pinned to worker 0
  EN-->>CC: reply: call the Agent tool ×2
  par two subagents in parallel
    CC->>GW: sub-a turn 1 (agent-id = a)
    GW->>CL: generate(program_id = a, parent = root)
    CL->>FE: Session-ID: a · Parent-Session-ID: root
    FE->>EN: program a created (parent = root), pinned
  and
    CC->>GW: sub-b turn 1 (agent-id = b)
    GW->>CL: generate(program_id = b, parent = root)
    CL->>FE: Session-ID: b · Parent-Session-ID: root
    FE->>EN: program b created, pinned
  end
  Note over GW: serial within a program, concurrent across programs (used to be a 409)
  loop tool-call turns of sub-a / sub-b
    CC->>GW: turn n
    FE->>EN: still pinned to the same GPU, prefix hit
  end
  CC->>GW: sub-a's last turn, finish_reason = stop
  GW->>CL: finalize_program(a) (rule ①)
  CL->>FE: X-Dynamo-Session-Final: true (a)
  FE-->>FE: program a removed, capacity returned at once
  CC->>GW: root resumes (the Agent tool returned)
  GW->>CL: release the still-idle child b (rule ②), then generate(root)
  FE->>EN: root still pinned to worker 0
  alt session ends normally
    GW->>GW: finalize_session: let in-flight turns finish (≤ 60 s)
  else session times out / is aborted (abort_session)
    GW->>CL: cancel the in-flight generate (asyncio cancel)
    CL->>CL: ray.cancel → the server actor drops the HTTP request
    FE-->>FE: request rolled back (cancel_request), no longer charged
  end
  GW->>CL: release the tree: children first, root final (rule ③)
  CL->>FE: X-Dynamo-Session-Final: true (root)
  FE-->>GW: programs of this session back to zero
''',
}

TXT = {
 "zh": dict(
  h2="二 · Subagent 支持：整体流程与时序",
  lead=("Claude Code 一派出 subagent，每个 subagent 就带着自己的 <code>x-claude-code-agent-id</code> 发请求。未改动的链路里这些头在 uni-agent 的 gateway 就终止了，"
        "ThunderAgent 看到的是一堆互不相干、而且没人结束的 program。这次的改动全部落在 verl-recipe 的 Gateway 适配器和 V1 client 里（蓝色框），"
        "让每一跳都把“这是谁、谁派的、什么时候结束”带下去；dynamo 和 uni-agent 不改。细节见"
        "<a href=\"https://claude.ai/artifact/STnXtz2gUcFs6PwX1C685s\">实现说明</a>。"),
  flow_cap="整体流程：一个 rollout 就是一棵 program 树。Gateway 适配器和 TA server 都是 Ray actor，每个 session 一个适配器实例。蓝色框是本次改动的组件（全部在 verl-recipe 的 Gateway 适配器与 V1 client / TA server 里），灰色框（Claude Code、Dynamo 原生 TA 插件、引擎）未改。三条释放规则都在适配器里，不依赖 router 配合；③ 是修掉数据污染的那条：关闭 session 时取消还在 frontend 里排队的 turn，否则该 program 会一直占着 TA 的容量核算。",
  seq_cap="一次 rollout 的时序：主 agent 派两个 subagent，subagent 返回即释放，主 agent 恢复时清掉剩余空闲子，最后按子先根后释放；右下的分支是 90 分钟超时时的取消路径。步骤编号对应上图的规则 ①②③。",
  ref=("见第四节。", "见第五节。")),
 "en": dict(
  h2="2 · Subagent support: overall flow and sequence",
  lead=("As soon as Claude Code dispatches a subagent, each subagent sends its own requests under its own <code>x-claude-code-agent-id</code>. In the unmodified stack those "
        "headers stop at the uni-agent gateway, so ThunderAgent sees unrelated programs that nobody ever ends. Everything added here lives in the verl-recipe Gateway "
        "adapter and V1 client (blue boxes): every hop carries who the request is, who dispatched it and when it ends; dynamo and uni-agent are untouched. "
        "Details in the <a href=\"https://claude.ai/artifact/STnXtz2gUcFs6PwX1C685s\">implementation notes</a>."),
  flow_cap="Overall flow: one rollout is one program tree. The Gateway adapter and the TA server are Ray actors, one adapter per session. Blue boxes are the components changed in this work (all inside verl-recipe: the Gateway adapter and the V1 client / TA server); grey ones (Claude Code, the native Dynamo TA plugin, the engines) are untouched. All three release rules live in the adapter and need no router cooperation; rule ③ is the one that removed the data contamination: closing a session cancels turns still queued at the frontend, otherwise their programs stay charged against ThunderAgent's capacity model.",
  seq_cap="One rollout: the root dispatches two subagents, each is released the moment it returns, the root's resumption clears any remaining idle child, and the close releases children before the root. The lower branch is the cancellation path taken at the 90-minute timeout. Rule numbers match the flow chart.",
  ref=None),
}

ZH_NUM = "一二三四五六七八九"

def section(lang):
    t = TXT[lang]
    return ("<!-- subagent-flow -->\n"
            f'<h2>{t["h2"]}</h2>\n<p>{t["lead"]}</p>\n'
            f'<figure><pre class="mermaid">\n{FLOW[lang]}</pre><figcaption>{t["flow_cap"]}</figcaption></figure>\n'
            f'<figure><pre class="mermaid">\n{SEQ[lang]}</pre><figcaption>{t["seq_cap"]}</figcaption></figure>\n'
            "<!-- /subagent-flow -->")

def put(html, lang):
    sec = section(lang)
    if "<!-- subagent-flow -->" in html:
        a, b = html.index("<!-- subagent-flow -->"), html.index("<!-- /subagent-flow -->") + len("<!-- /subagent-flow -->")
        return html[:a] + sec + html[b:]
    if lang == "zh":
        for old in reversed(ZH_NUM[1:7]):  # 二..七 -> 三..八
            html = html.replace(f"<h2>{old} ·", f"<h2>{ZH_NUM[ZH_NUM.index(old) + 1]} ·")
        html = html.replace(*TXT["zh"]["ref"])
    else:
        for old in range(7, 1, -1):  # 2..7 -> 3..8
            html = html.replace(f"<h2>{old} ·", f"<h2>{old + 1} ·")
        html = html.replace("section 4", "section 5").replace("section 2", "section 3")
    if "pre.mermaid" not in html:
        html = html.replace("</style>", "pre.mermaid{white-space:pre-wrap;font-size:12px}\n.mermaid-diagram svg{max-width:100%;height:auto}\n</style>", 1)
    i = html.index("<!-- sweep-section -->")
    return html[:i] + sec + "\n\n" + html[i:]

if __name__ == "__main__":
    for path, lang in zip(sys.argv[1:3], ("zh", "en")):
        html = open(path, encoding="utf-8").read()
        out = put(html, lang)
        open(path, "w", encoding="utf-8").write(out)
        print(lang, len(out), re.findall(r"<h2>([^<]{1,14})", out))
