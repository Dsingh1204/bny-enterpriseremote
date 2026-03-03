/**
 * Enterprise Remote Support Server
 * Central relay server (like BeyondTrust B Series Appliance)
 * 
 * Features:
 * - Session management with access codes
 * - Admin/Rep authentication (JWT)
 * - Client agent connections
 * - Screen streaming relay
 * - Remote control relay
 * - File transfer
 * - Chat messaging
 * - Session logging & recording
 */

const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const cors = require('cors');
const { v4: uuidv4 } = require('uuid');
const path = require('path');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const fs = require('fs');
require('dotenv').config();

const app = express();
const server = http.createServer(app);

const JWT_SECRET = process.env.JWT_SECRET || 'enterprise-remote-support-secret-key';
const PORT = process.env.PORT || 3000;

const io = new Server(server, {
  cors: { origin: '*', methods: ['GET', 'POST'] },
  maxHttpBufferSize: 50e6 // 50MB for file transfers
});

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, '../public')));

// ============== DATA STORES ==============
const sessions = new Map();        // sessionId -> session data
const clients = new Map();         // clientId -> client info
const admins = new Map();          // adminId -> admin info
const socketToEntity = new Map();  // socketId -> { type, id }
const sessionLogs = new Map();     // sessionId -> log entries

// Default admin accounts (in production, use database)
const adminAccounts = new Map([
  ['admin', { password: bcrypt.hashSync('admin123', 10), name: 'Administrator', role: 'admin' }],
  ['tech1', { password: bcrypt.hashSync('tech123', 10), name: 'Tech Support 1', role: 'tech' }]
]);

// ============== UTILITY FUNCTIONS ==============
function generateAccessCode() {
  return Math.random().toString(36).substring(2, 10).toUpperCase();
}

function generateClientId() {
  return 'CLI-' + uuidv4().substring(0, 8).toUpperCase();
}

function logSession(sessionId, event, data = {}) {
  if (!sessionLogs.has(sessionId)) {
    sessionLogs.set(sessionId, []);
  }
  const entry = {
    timestamp: new Date().toISOString(),
    event,
    ...data
  };
  sessionLogs.get(sessionId).push(entry);
  console.log(`[${sessionId}] ${event}:`, JSON.stringify(data));
}

// ============== REST API ENDPOINTS ==============

// Admin login
app.post('/api/auth/login', async (req, res) => {
  const { username, password } = req.body;
  const account = adminAccounts.get(username);
  
  if (!account || !bcrypt.compareSync(password, account.password)) {
    return res.status(401).json({ error: 'Invalid credentials' });
  }
  
  const token = jwt.sign(
    { username, name: account.name, role: account.role },
    JWT_SECRET,
    { expiresIn: '8h' }
  );
  
  res.json({ token, name: account.name, role: account.role });
});

// Get active sessions
app.get('/api/sessions', (req, res) => {
  const sessionList = [];
  sessions.forEach((session, id) => {
    sessionList.push({
      id,
      accessCode: session.accessCode,
      clientInfo: session.clientInfo,
      status: session.adminSocket ? 'active' : 'waiting',
      createdAt: session.createdAt,
      adminConnected: !!session.adminSocket
    });
  });
  res.json(sessionList);
});

// Get session logs
app.get('/api/sessions/:id/logs', (req, res) => {
  const logs = sessionLogs.get(req.params.id) || [];
  res.json(logs);
});

// Get connected clients
app.get('/api/clients', (req, res) => {
  const clientList = [];
  clients.forEach((client, id) => {
    clientList.push({
      id,
      ...client,
      socketConnected: !!client.socketId
    });
  });
  res.json(clientList);
});

// ============== SOCKET.IO HANDLERS ==============

io.on('connection', (socket) => {
  console.log(`Socket connected: ${socket.id}`);

  // -------- CLIENT AGENT EVENTS --------
  
  // Client registers with the server
  socket.on('client:register', (data, callback) => {
    const clientId = generateClientId();
    const accessCode = generateAccessCode();
    const sessionId = uuidv4();
    
    const clientInfo = {
      id: clientId,
      hostname: data.systemInfo?.hostname || 'Unknown',
      platform: data.systemInfo?.platform || 'Unknown',
      os: data.systemInfo?.os || 'Unknown',
      ip: socket.handshake.address,
      socketId: socket.id,
      registeredAt: new Date().toISOString()
    };
    
    clients.set(clientId, clientInfo);
    
    const session = {
      id: sessionId,
      accessCode,
      clientId,
      clientSocket: socket,
      clientInfo,
      adminSocket: null,
      adminInfo: null,
      createdAt: new Date().toISOString(),
      controlEnabled: false,
      features: {
        screenShare: true,
        remoteControl: false,
        fileTransfer: false,
        chat: true
      }
    };
    
    sessions.set(sessionId, session);
    socketToEntity.set(socket.id, { type: 'client', id: clientId, sessionId });
    
    logSession(sessionId, 'CLIENT_REGISTERED', { clientId, hostname: clientInfo.hostname });
    
    callback({
      success: true,
      clientId,
      sessionId,
      accessCode
    });
  });

  // Client sends screen frame
  socket.on('screen:frame', (data) => {
    const entity = socketToEntity.get(socket.id);
    if (!entity || entity.type !== 'client') return;
    
    const session = sessions.get(entity.sessionId);
    if (session?.adminSocket) {
      session.adminSocket.emit('screen:frame', data);
    }
  });

  // Client sends system info update
  socket.on('client:sysinfo', (data) => {
    const entity = socketToEntity.get(socket.id);
    if (!entity) return;
    
    const session = sessions.get(entity.sessionId);
    if (session?.adminSocket) {
      session.adminSocket.emit('client:sysinfo', data);
    }
  });

  // -------- ADMIN/REP EVENTS --------

  // Admin joins session with access code
  socket.on('admin:join', (data, callback) => {
    const { accessCode, token } = data;
    
    // Verify JWT token
    let adminInfo;
    try {
      adminInfo = jwt.verify(token, JWT_SECRET);
    } catch (err) {
      return callback({ success: false, error: 'Invalid or expired token' });
    }
    
    // Find session by access code
    let targetSession = null;
    sessions.forEach((session) => {
      if (session.accessCode === accessCode) {
        targetSession = session;
      }
    });
    
    if (!targetSession) {
      return callback({ success: false, error: 'Invalid access code' });
    }
    
    if (targetSession.adminSocket) {
      return callback({ success: false, error: 'Session already has an admin connected' });
    }
    
    targetSession.adminSocket = socket;
    targetSession.adminInfo = adminInfo;
    
    socketToEntity.set(socket.id, { type: 'admin', sessionId: targetSession.id });
    
    logSession(targetSession.id, 'ADMIN_CONNECTED', { admin: adminInfo.name });
    
    // Notify client
    if (targetSession.clientSocket) {
      targetSession.clientSocket.emit('admin:connected', {
        adminName: adminInfo.name
      });
    }
    
    callback({
      success: true,
      sessionId: targetSession.id,
      clientInfo: targetSession.clientInfo
    });
  });

  // Admin requests control
  socket.on('control:request', (data) => {
    const entity = socketToEntity.get(socket.id);
    if (!entity || entity.type !== 'admin') return;
    
    const session = sessions.get(entity.sessionId);
    if (session?.clientSocket) {
      logSession(session.id, 'CONTROL_REQUESTED', { admin: session.adminInfo?.name });
      session.clientSocket.emit('control:request', {
        adminName: session.adminInfo?.name
      });
    }
  });

  // Control granted/denied by client
  socket.on('control:response', (data) => {
    const entity = socketToEntity.get(socket.id);
    if (!entity) return;
    
    const session = sessions.get(entity.sessionId);
    if (session) {
      session.controlEnabled = data.granted;
      session.features.remoteControl = data.granted;
      
      logSession(session.id, data.granted ? 'CONTROL_GRANTED' : 'CONTROL_DENIED');
      
      if (session.adminSocket) {
        session.adminSocket.emit('control:response', data);
      }
    }
  });

  // Admin sends mouse event
  socket.on('mouse:event', (data) => {
    const entity = socketToEntity.get(socket.id);
    if (!entity || entity.type !== 'admin') return;
    
    const session = sessions.get(entity.sessionId);
    if (session?.controlEnabled && session.clientSocket) {
      session.clientSocket.emit('mouse:event', data);
    }
  });

  // Admin sends keyboard event
  socket.on('keyboard:event', (data) => {
    const entity = socketToEntity.get(socket.id);
    if (!entity || entity.type !== 'admin') return;
    
    const session = sessions.get(entity.sessionId);
    if (session?.controlEnabled && session.clientSocket) {
      session.clientSocket.emit('keyboard:event', data);
    }
  });

  // Chat messages
  socket.on('chat:message', (data) => {
    const entity = socketToEntity.get(socket.id);
    if (!entity) return;
    
    const session = sessions.get(entity.sessionId);
    if (!session) return;
    
    const message = {
      id: uuidv4(),
      sender: entity.type,
      senderName: entity.type === 'admin' ? session.adminInfo?.name : session.clientInfo?.hostname,
      text: data.text,
      timestamp: new Date().toISOString()
    };
    
    logSession(session.id, 'CHAT_MESSAGE', { sender: message.senderName, text: data.text });
    
    // Send to both parties
    if (session.clientSocket) session.clientSocket.emit('chat:message', message);
    if (session.adminSocket) session.adminSocket.emit('chat:message', message);
  });

  // File transfer initiate
  socket.on('file:start', (data) => {
    const entity = socketToEntity.get(socket.id);
    if (!entity) return;
    
    const session = sessions.get(entity.sessionId);
    if (!session) return;
    
    const target = entity.type === 'admin' ? session.clientSocket : session.adminSocket;
    if (target) {
      logSession(session.id, 'FILE_TRANSFER_START', { 
        from: entity.type, 
        filename: data.filename,
        size: data.size 
      });
      target.emit('file:start', { ...data, sender: entity.type });
    }
  });

  // File chunk
  socket.on('file:chunk', (data) => {
    const entity = socketToEntity.get(socket.id);
    if (!entity) return;
    
    const session = sessions.get(entity.sessionId);
    if (!session) return;
    
    const target = entity.type === 'admin' ? session.clientSocket : session.adminSocket;
    if (target) {
      target.emit('file:chunk', data);
    }
  });

  // File transfer complete
  socket.on('file:complete', (data) => {
    const entity = socketToEntity.get(socket.id);
    if (!entity) return;
    
    const session = sessions.get(entity.sessionId);
    if (!session) return;
    
    logSession(session.id, 'FILE_TRANSFER_COMPLETE', { filename: data.filename });
    
    const target = entity.type === 'admin' ? session.clientSocket : session.adminSocket;
    if (target) {
      target.emit('file:complete', data);
    }
  });

  // End session
  socket.on('session:end', (data) => {
    const entity = socketToEntity.get(socket.id);
    if (!entity) return;
    
    const session = sessions.get(entity.sessionId);
    if (session) {
      logSession(session.id, 'SESSION_ENDED', { by: entity.type, reason: data?.reason });
      
      if (session.clientSocket) {
        session.clientSocket.emit('session:ended', { reason: data?.reason || 'Session ended' });
      }
      if (session.adminSocket) {
        session.adminSocket.emit('session:ended', { reason: data?.reason || 'Session ended' });
      }
    }
  });

  // Handle disconnect
  socket.on('disconnect', () => {
    const entity = socketToEntity.get(socket.id);
    if (!entity) return;
    
    const session = sessions.get(entity.sessionId);
    if (session) {
      if (entity.type === 'client') {
        logSession(session.id, 'CLIENT_DISCONNECTED');
        if (session.adminSocket) {
          session.adminSocket.emit('client:disconnected');
        }
        clients.delete(entity.id);
        sessions.delete(entity.sessionId);
      } else if (entity.type === 'admin') {
        logSession(session.id, 'ADMIN_DISCONNECTED');
        session.adminSocket = null;
        session.adminInfo = null;
        session.controlEnabled = false;
        if (session.clientSocket) {
          session.clientSocket.emit('admin:disconnected');
        }
      }
    }
    
    socketToEntity.delete(socket.id);
    console.log(`Socket disconnected: ${socket.id}`);
  });
});

// Start server
server.listen(PORT, '0.0.0.0', () => {
  console.log(`
╔═══════════════════════════════════════════════════════════╗
║     Enterprise Remote Support Server                      ║
║     (Similar to BeyondTrust/Bomgar Architecture)          ║
╠═══════════════════════════════════════════════════════════╣
║  Server running on: http://localhost:${PORT}                 ║
║  Admin Console:     http://localhost:${PORT}/admin           ║
║  API Endpoints:     http://localhost:${PORT}/api             ║
╠═══════════════════════════════════════════════════════════╣
║  Default Accounts:                                        ║
║    admin / admin123 (Administrator)                       ║
║    tech1 / tech123  (Tech Support)                        ║
╚═══════════════════════════════════════════════════════════╝
  `);
});
