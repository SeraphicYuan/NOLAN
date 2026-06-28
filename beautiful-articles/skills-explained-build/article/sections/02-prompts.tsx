import { Section, Aside, CodeBlock, Raw } from "reacticle";
import { VersusPair } from "../figures";

// Section 02 — What are prompts?  Prose + code; the ephemeral-vs-persistent
// contrast is the reusable VersusPair figure (data only).

export function SectionPrompts() {
  return (
    <Section index="02" title="What are prompts?">
      <p>
        If Skills are the training manuals Claude keeps on the shelf, prompts are the
        conversation you have while the work is happening. A <strong>prompt</strong> is the
        instruction you give Claude in natural language during a chat — context and
        direction supplied in the moment. Prompts are ephemeral, conversational, and
        reactive: you say what you need, Claude responds, and you steer from there.
      </p>

      <p>
        That immediacy is the whole point. You don't set anything up, you don't save
        anything — you just talk. Prompts are the right tool whenever the request lives
        inside the conversation you're already having:
      </p>
      <ul>
        <li>
          <strong>One-off requests</strong> — "Summarize this article."
        </li>
        <li>
          <strong>Conversational refinement</strong> — "Make that tone more professional."
        </li>
        <li>
          <strong>Immediate context</strong> — "Analyze this data and identify trends."
        </li>
        <li>
          <strong>Ad-hoc instructions</strong> — "Format this as a bulleted list."
        </li>
      </ul>

      <p>
        Prompts don't have to be short, though. A good one can be a detailed brief that
        spells out exactly what you want back — what to look for, how to organize the
        answer, and what context Claude should assume. Here's a thorough example: a
        prompt that asks for a full security review of some code.
      </p>

      <CodeBlock
        language="text"
        title="Example prompt: security review"
        code={`Please conduct a comprehensive security review of this code. I'm looking for:

1. Common vulnerabilities including:
   - Injection flaws (SQL, command, XSS, etc.)
   - Authentication and authorization issues
   - Sensitive data exposure
   - Security misconfigurations
   - Broken access control
   - Cryptographic failures
   - Input validation problems
   - Error handling and logging issues

2. For each issue you find, please provide:
   - Severity level (Critical/High/Medium/Low)
   - Location in the code (line numbers or function names)
   - Explanation of why it's a security risk and how it could be exploited
   - Specific fix recommendation with code examples where possible
   - Best practice guidance to prevent similar issues

3. Code context: [Describe what the code does, the language/framework, and the
   environment it runs in - e.g., "This is a Node.js REST API that handles user
   authentication and processes payment data"]

4. Additional considerations:
   - Are there any OWASP Top 10 vulnerabilities present?
   - Does the code follow security best practices for [specific framework/language]?
   - Are there any dependencies with known vulnerabilities?

Please prioritize findings by severity and potential impact.`}
      />

      <p>
        Notice the catch hiding inside that example: it's a brilliant prompt, but you'd
        have to retype it every time you wanted a security review. Prompts are powerful
        precisely because they're live — and that same liveness means they vanish when
        the conversation ends.
      </p>

      <Raw title="A prompt lives inside one conversation; a Skill persists across many">
        <VersusPair
          left={{
            sticker: "Prompt",
            title: "Lives in one conversation",
            body: "A live instruction — powerful, but gone when the chat ends. You'd retype it next time.",
            items: ["“Run a security review on this.”", "…gone when the chat ends"],
          }}
          right={{
            sticker: "Skill",
            title: "Persists across many",
            body: "Saved once, reached for anytime — the same expertise across every conversation.",
            items: ["Today's chat", "Last week", "A new project"],
          }}
        />
      </Raw>

      <Aside tone="note" label="Pro tip">
        Prompts are your primary way of interacting with Claude, but they don't persist
        across conversations. For repeated workflows or specialized knowledge, consider
        capturing prompts as Skills or project instructions.
      </Aside>

      <p>
        So how do you know when a prompt has outgrown the chat? The signal is repetition.
        The moment you catch yourself typing the same instructions for the third or fourth
        time, the prompt is really a procedure — and procedures belong somewhere they can
        be reused.
      </p>

      <Aside tone="principle" label="When to use a Skill instead">
        If you find yourself typing the same prompt repeatedly across multiple
        conversations, it's time to create a Skill. Transform recurring instructions like
        "review this code for security vulnerabilities using OWASP standards" or "format
        this analysis with executive summary, key findings, and recommendations" into
        Skills. This saves re-explaining procedures each time and ensures consistent
        execution.
      </Aside>
    </Section>
  );
}
