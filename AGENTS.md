# Directory Restrictions
- NEVER read, write, edit, or create files outside the current project directory
- NEVER use absolute paths that reference locations outside this folder
- All paths must be relative to the project root or within its subdirectories
- If a task requires accessing external files, ask for permission first

You can also combine it with bash restrictions:

# Workspace Boundaries
Stay within D:\ClaudeProjects\NOLAN and its subdirectories only.
- Do not access parent directories (no `../` paths leading outside the project)
- Do not use absolute paths to system directories
- All bash commands must operate within the project folder

# Python Environment Rules
- This project uses a Conda environment named `nolan`.
- Always use the python binary located at: `D:\env\nolan\python.exe`
- Always use pip from: `D:\env\nolan\Scripts\pip.exe`
- Do not use system python or create a new .venv folder.

# Documentation Rules
After completing any new feature, update the corresponding documentation:
- Default update goes to "IMPLEMENTATION_STATUS.md"
- If there's no corresponding documentation (*.md), create it when necessary
- Keep updates concise: what changed, usage example, benefits

# Tool Permissions
- Before asking for user approval on any tool use, check `.claude/settings.local.json` first
- If the command pattern is listed in the `permissions.allow` array, proceed without asking
- Only ask for approval if the command is NOT covered by existing permissions

# Claude Domaine
- Strictly stay within this folder

# Notification Rule
- When requiring user approval for any action, play a notification sound first
- Use PowerShell to play a 3-tone ascending sound: `powershell -c "[console]::beep(1000,200); [console]::beep(1200,200); [console]::beep(1500,300)"`
- This helps alert the user that attention is needed

