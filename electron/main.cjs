const { app, BrowserWindow } = require('electron');
const path = require('path');

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false, // For simple apps; consider enabling for security if loading external content
    },
  });

  // Check if we are in development mode
  const isDev = !app.isPackaged;

  if (isDev) {
    mainWindow.loadURL('http://localhost:8080');
    // Open the DevTools.
    mainWindow.webContents.openDevTools();
  } else {
    // In production, load the index.html from the dist folder
    // The dist folder will be one level up from this file (electron/main.cjs) -> dist/index.html
    // However, when packaged, the structure depends on electron-builder configuration.
    // Usually, we point to the build output.
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

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
