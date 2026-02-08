### About

Secure (E2E) serverless endpoint for ComfyUI

**1. Set Encryption Key**
```bash
export ENCRYPTION_KEY="your-fernet-key"
```

**2. Image Editing (1 Image)**
```bash
python client.py --workflow workflow.json --img photo.jpg --prompt "make it a sunset"
```

**3. Image Merging (Multiple Images)**
```bash
# Images are mapped to LoadImage nodes in order of Node ID
python client.py --workflow workflow_2.json --img background.jpg subject.jpg --prompt "merge them"
```

**4. Debug Mode (Disables Encryption)**
```bash
python client.py --img photo.jpg --prompt "test" --debug
```

**5. GUI Access (via SSH Tunnel)**
```bash
ssh -L 8188:127.0.0.1:8188 root@<POD_IP> -p <PORT>
# Open http://127.0.0.1:8188 in your browser
```
