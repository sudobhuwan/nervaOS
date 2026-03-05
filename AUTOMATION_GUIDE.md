# 🤖 NervaOS Automation System Guide

## **Overview**

NervaOS includes a powerful automation engine that:
- ✅ **Executes workflows** based on time, events, and conditions
- ✅ **Learns your patterns** and suggests automations
- ✅ **Acts proactively** to optimize your system
- ✅ **Respects safety** - never touches system files without permission

---

## **Quick Start**

### **1. Enable Example Workflows**

```bash
# Copy example workflows
cp /media/eklavya/STORAGE6/NervaOS/config/workflows.example.yaml \
   ~/.config/nervaos/automation/workflows.yaml

# Edit to your needs
nano ~/.config/nervaos/automation/workflows.yaml

# Restart daemon to load
systemctl --user restart nerva-service
```

### **2. Check Status**

```bash
# View logs
journalctl --user -u nerva-service -f | grep automation
```

---

## **Workflow Anatomy**

```yaml
- name: "My Workflow"           # Human-readable name
  description: "What it does"   # Optional description
  enabled: true                 # true/false
  
  trigger:                      # WHEN to run
    type: "time"                # Trigger type
    condition:
      time: "09:00"             # Trigger condition
  
  actions:                      # WHAT to do
    - type: "open"              # Action type
      params:
        app: "google-chrome"    # Action parameters
```

---

## **Trigger Types**

### **1. Time-Based Triggers**

**Run at specific time daily:**
```yaml
trigger:
  type: "time"
  condition:
    time: "09:00"  # HH:MM format (24-hour)
```

**Run on weekdays:**
```yaml
trigger:
  type: "weekday"
  condition:
    days: "Mon-Fri"  # Or "Mon,Wed,Fri"
    time: "09:00"
```

### **2. Event-Based Triggers**

**When system metrics exceed threshold:**
```yaml
trigger:
  type: "event"
  condition:
    metric: "ram_percent"  # ram_percent, cpu_percent, disk_percent
    operator: ">"          # >, <, ==
    value: 90              # Threshold
```

**Available metrics:**
- `ram_percent` - RAM usage percentage
- `cpu_percent` - CPU usage percentage
- `disk_percent` - Disk usage percentage

### **3. File-Based Triggers**

**When folder has too many files:**
```yaml
trigger:
  type: "file_count"
  condition:
    path: "~/Downloads"
    count: 50  # Trigger when > 50 files
```

### **4. Battery Triggers**

**When battery is low:**
```yaml
trigger:
  type: "battery"
  condition:
    level: 20  # Trigger when < 20%
```

### **5. App Launch Triggers**

**When specific app opens:**
```yaml
trigger:
  type: "app_launch"
  condition:
    app: "steam"  # App name (case-insensitive)
```

---

## **Action Types**

### **1. Open Application**

```yaml
- type: "open"
  params:
    app: "google-chrome"
    # or with arguments:
    app: "code ~/Projects/myproject"
```

### **2. Execute Command**

```yaml
- type: "execute"
  params:
    command: "docker-compose up -d"
    # Only safe, whitelisted commands allowed
```

### **3. Close Application**

```yaml
- type: "close"
  params:
    app: "chrome"  # Kills all processes matching name
```

### **4. Organize Folder**

```yaml
- type: "organize"
  params:
    path: "~/Downloads"
    # Automatically sorts by file type
```

### **5. Send Notification**

```yaml
- type: "notify"
  params:
    message: "Your custom message here"
```

### **6. Ask AI**

```yaml
- type: "ask_ai"
  params:
    query: "What's using all my RAM?"
    # AI analyzes and sends notification with answer
```

### **7. Show Suggestion**

```yaml
- type: "suggest"
  params:
    suggestion: "💡 Time to take a break!"
```

---

## **Example Workflows**

### **1. Morning Routine**

```yaml
- name: "Developer Morning Routine"
  description: "Start all dev tools at 9 AM weekdays"
  enabled: true
  trigger:
    type: "weekday"
    condition:
      days: "Mon-Fri"
      time: "09:00"
  actions:
    - type: "open"
      params:
        app: "code ~/Projects/main"
    - type: "open"
      params:
        app: "google-chrome --new-window github.com"
    - type: "execute"
      params:
        command: "docker-compose up -d"
    - type: "notify"
      params:
        message: "☕ Dev environment ready!"
```

### **2. Auto-Cleanup**

```yaml
- name: "Auto-Organize Downloads"
  description: "Clean Downloads when messy"
  enabled: true
  trigger:
    type: "file_count"
    condition:
      path: "~/Downloads"
      count: 50
  actions:
    - type: "organize"
      params:
        path: "~/Downloads"
    - type: "notify"
      params:
        message: "🗂️ Downloads organized!"
```

### **3. Smart Battery Saver**

```yaml
- name: "Battery Saver"
  description: "Optimize when battery low"
  enabled: true
  trigger:
    type: "battery"
    condition:
      level: 20
  actions:
    - type: "execute"
      params:
        command: "brightnessctl set 30%"
    - type: "close"
      params:
        app: "spotify"
    - type: "close"
      params:
        app: "chrome"
    - type: "notify"
      params:
        message: "🔋 Battery saver ON"
```

### **4. Gaming Mode**

```yaml
- name: "Gaming Optimization"
  description: "Close background apps when gaming"
  enabled: true
  trigger:
    type: "app_launch"
    condition:
      app: "steam"
  actions:
    - type: "close"
      params:
        app: "chrome"
    - type: "close"
      params:
        app: "slack"
    - type: "notify"
      params:
        message: "🎮 Gaming mode activated!"
```

### **5. AI-Powered System Check**

```yaml
- name: "Daily System Health Check"
  description: "Ask AI to analyze system every evening"
  enabled: true
  trigger:
    type: "time"
    condition:
      time: "18:00"
  actions:
    - type: "ask_ai"
      params:
        query: "Analyze my system health. Any issues I should know about?"
```

---

## **Pattern Learning**

NervaOS **automatically learns** your behavior patterns!

### **What It Learns:**

1. **App Sequences**
   - "You always open Code → Chrome → Terminal"
   - Suggests: "Automate this sequence?"

2. **Time Routines**
   - "You open Spotify at 2 PM every day"
   - Suggests: "Create afternoon music routine?"

3. **Condition-Action Patterns**
   - "When Downloads has 50+ files, you organize it"
   - Suggests: "Auto-organize Downloads?"

### **How It Works:**

```
User Opens VS Code
  ↓
User Opens Chrome (within 5 min)
  ↓
User Opens Terminal (within 5 min)
  ↓ (Happens 5+ times)
NervaOS Notices Pattern
  ↓
💡 Suggestion Notification:
"Automate Routine?"
Open Code → Chrome → Terminal
(Detected 5 times, 80% confidence)
👍 Accept | ❌ Dismiss
  ↓ (User Accepts)
Workflow Created Automatically!
```

### **Accepting Suggestions:**

When you get a suggestion notification:
1. Click "Accept" (or react with 👍)
2. Workflow is created automatically
3. Appears in your workflows.yaml
4. Starts working immediately!

---

## **Safety Guarantees**

### **✅ What Automation CAN Do:**

- ✅ Open/close applications
- ✅ Execute safe commands (docker, git, ls, etc.)
- ✅ Organize files in ~/
- ✅ Read system metrics
- ✅ Send notifications

### **❌ What Automation CANNOT Do:**

- ❌ Modify system files (/etc, /usr, /bin)
- ❌ Run sudo commands
- ❌ Install/remove packages
- ❌ Change permissions (chmod/chown)
- ❌ Delete files (only organize)

### **Cooldown Protection:**

- Workflows have 1-hour cooldown
- Prevents infinite loops
- Battery-critical workflows can override

---

## **Advanced: Chaining Workflows**

You can create complex automation chains:

```yaml
# Step 1: Morning wake-up
- name: "Morning Wake"
  trigger:
    type: "time"
    condition:
      time: "08:00"
  actions:
    - type: "notify"
      params:
        message: "Good morning! Starting your day..."
    - type: "ask_ai"
      params:
        query: "What's my schedule today?"

# Step 2: Dev environment (30 min later)
- name: "Dev Environment"
  trigger:
    type: "time"
    condition:
      time: "08:30"
  actions:
    - type: "open"
      params:
        app: "code"
    - type: "execute"
      params:
        command: "docker-compose up -d"

# Step 3: Standup reminder
- name: "Standup Reminder"
  trigger:
    type: "time"
    condition:
      time: "09:45"
  actions:
    - type: "notify"
      params:
        message: "🗣️ Standup in 15 minutes!"
```

---

## **Debugging**

### **Check if workflows loaded:**

```bash
# View daemon logs
journalctl --user -u nerva-service | grep -i workflow

# Should see:
# "Loaded 5 workflows"
# "Automation engine started"
```

### **Test a workflow manually:**

1. Open DBus inspector: `d-feet`
2. Connect to: `com.nervaos.daemon`
3. Call method: `AskAI` with query: "test automation"

### **Common Issues:**

**Workflow not triggering:**
- Check `enabled: true`
- Verify time format (24-hour HH:MM)
- Check daemon is running: `systemctl --user status nerva-service`

**Action fails:**
- Check command is in whitelist
- Verify app name is correct (lowercase)
- Check logs for specific error

---

## **Tips & Best Practices**

### **1. Start Small**

Begin with 1-2 simple workflows:
```yaml
- name: "Test Notification"
  trigger:
    type: "time"
    condition:
      time: "10:00"
  actions:
    - type: "notify"
      params:
        message: "Test workflow works!"
```

### **2. Use Variables**

```yaml
params:
  path: "~/Downloads"  # ~ expands to home
  command: "ls ~/Projects/myproject"
```

### **3. Combine Actions**

```yaml
actions:
  - type: "execute"
    params:
      command: "docker ps"
  - type: "notify"
    params:
      message: "Docker status checked"
  - type: "open"
    params:
      app: "google-chrome localhost:3000"
```

### **4. Let It Learn**

- Leave pattern learning ON
- Accept good suggestions
- Dismiss bad ones (improves learning)

---

## **What's Next?**

- 🔜 Voice-activated workflows
- 🔜 Calendar integration
- 🔜 Web dashboard for workflow management
- 🔜 Marketplace for sharing workflows

---

## **Support**

Questions? Check:
- GitHub Issues: `nervaos/nervaos`
- Logs: `~/.config/nervaos/automation/`
- Patterns: `~/.config/nervaos/automation/learned_patterns.json`

---

**You now have a fully autonomous AI OS that works FOR you!** 🚀
