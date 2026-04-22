const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('desktopBridge', {
  minimizeWindow: () => ipcRenderer.invoke('window:minimize'),
  closeWindow: () => ipcRenderer.invoke('window:close'),
  togglePin: () => ipcRenderer.invoke('window:pin'),
  runTask: (task) => ipcRenderer.invoke('system:runTask', task),
  chatAssistant: (prompt) => ipcRenderer.invoke('assistant:chat', prompt),
  tts: (text) => ipcRenderer.invoke('assistant:tts', text),
  onAssistantSpeak: (callback) => {
    ipcRenderer.on('assistant:speak', (_event, text) => {
      callback(text);
    });
  }
});