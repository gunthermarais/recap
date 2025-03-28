const express = require('express');
const cors = require('cors');
const { Client } = require('whatsapp-web.js');
const qrcode = require('qrcode');

const app = express();
app.use(cors());
app.use(express.json());

// Initialize WhatsApp client
console.log('Starting WhatsApp service...');
const client = new Client();
let qrCode = null;
let isReady = false;

// This event fires when WhatsApp Web needs a QR code to be scanned
client.on('qr', async (qr) => {
    console.log('New QR code generated');
    try {
        // Convert the QR code to a data URL
        qrCode = await qrcode.toDataURL(qr);
        console.log('QR code converted to data URL');
    } catch (err) {
        console.error('Error generating QR code:', err);
    }
});

client.on('ready', () => {
    isReady = true;
    console.log('WhatsApp client is ready!');
});

// Root route - update to show QR code if available
app.get('/', (req, res) => {
    res.send(`
        <html>
            <head>
                <title>WhatsApp Service</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
                    .container { max-width: 800px; margin: 0 auto; }
                    .status { padding: 20px; background: #f0f0f0; border-radius: 5px; margin: 20px 0; }
                    #qrcode { margin: 20px 0; }
                    img { max-width: 300px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>WhatsApp Service Status</h1>
                    <div class="status">
                        <p>Service is running on port 3000</p>
                        <div id="qrcode">
                            ${qrCode ? `<img src="${qrCode}" alt="WhatsApp QR Code">` : 'Waiting for QR code...'}
                        </div>
                        <p>Status: ${isReady ? 'Connected' : 'Waiting for connection'}</p>
                    </div>
                </div>
                <script>
                    // Refresh the page every 5 seconds until connected
                    if (!${isReady}) {
                        setTimeout(() => location.reload(), 5000);
                    }
                </script>
            </body>
        </html>
    `);
});

// QR code endpoint
app.get('/qr', (req, res) => {
    if (qrCode) {
        res.json({ qrCode });
    } else {
        res.status(404).json({ error: 'QR code not available yet' });
    }
});

// Status endpoint
app.get('/status', (req, res) => {
    res.json({ 
        connected: isReady,
        hasQR: qrCode !== null
    });
});

// Get all chats
app.get('/chats', async (req, res) => {
    if (!isReady) {
        return res.status(400).json({ error: 'WhatsApp client not ready' });
    }

    try {
        const chats = await client.getChats();
        const simplifiedChats = chats.map(chat => ({
            id: chat.id._serialized,
            name: chat.name,
            unreadCount: chat.unreadCount,
            timestamp: chat.timestamp,
            isGroup: chat.isGroup
        }));
        res.json(simplifiedChats);
    } catch (error) {
        console.error('Error fetching chats:', error);
        res.status(500).json({ error: 'Failed to fetch chats' });
    }
});

// Get unanswered messages
app.get('/unanswered', async (req, res) => {
    if (!isReady) {
        return res.status(400).json({ error: 'WhatsApp client not ready' });
    }

    try {
        const chats = await client.getChats();
        const unansweredMessages = [];

        for (const chat of chats) {
            if (chat.unreadCount > 0) {
                const messages = await chat.fetchMessages({ limit: chat.unreadCount });
                messages.forEach(msg => {
                    if (!msg.fromMe) {  // Message not from you
                        unansweredMessages.push({
                            chatName: chat.name,
                            chatId: chat.id._serialized,
                            message: msg.body,
                            timestamp: msg.timestamp,
                            from: msg.from
                        });
                    }
                });
            }
        }

        res.json(unansweredMessages);
    } catch (error) {
        console.error('Error fetching unanswered messages:', error);
        res.status(500).json({ error: 'Failed to fetch unanswered messages' });
    }
});

// Initialize the client
client.initialize();

const PORT = 3000;
app.listen(PORT, () => {
    console.log(`WhatsApp service running on port ${PORT}`);
    console.log(`Visit http://localhost:${PORT} to see service status`);
}); 