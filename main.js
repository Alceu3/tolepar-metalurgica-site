const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { execFile } = require('child_process');

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 430,
    height: 760,
    minWidth: 360,
    minHeight: 620,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    resizable: true,
    hasShadow: false,
    backgroundColor: '#00000000',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

function launchProgram(program) {
  return new Promise((resolve, reject) => {
    execFile(program, (error) => {
      if (error) {
        reject(error);
        return;
      }

      resolve();
    });
  });
}

ipcMain.handle('window:minimize', () => {
  if (mainWindow) {
    mainWindow.minimize();
  }
});

ipcMain.handle('window:close', () => {
  if (mainWindow) {
    mainWindow.close();
  }
});

ipcMain.handle('window:pin', () => {
  if (!mainWindow) {
    return false;
  }

  const next = !mainWindow.isAlwaysOnTop();
  mainWindow.setAlwaysOnTop(next, 'screen-saver');
  return next;
});

ipcMain.handle('system:runTask', async (_event, task) => {
  switch (task) {
    case 'open-notepad':
      await launchProgram('notepad.exe');
      return 'Bloco de Notas aberto.';
    case 'open-calculator':
      await launchProgram('calc.exe');
      return 'Calculadora aberta.';
    case 'open-browser':
      await shell.openExternal('https://www.bing.com');
      return 'Navegador aberto.';
    case 'tell-time':
      return `Agora sao ${new Date().toLocaleTimeString('pt-BR')}.`;
    default:
      throw new Error('Tarefa nao suportada.');
  }
});

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});