// arweave-poster.js
import express from 'express';
import Arweave from 'arweave';
import fs from 'fs/promises';

const app = express();
const PORT = 3600;

app.use(express.json());

const arweave = Arweave.init({
  host: 'localhost',
  port: 1984,
  protocol: 'http'
});

// Load key from disk
const wallet = JSON.parse(await fs.readFile('./arweave-keyfile.json', 'utf8'));

app.post('/post', async (req, res) => {
  const { data } = req.body;
  if (!data) return res.status(400).json({ error: 'Missing data' });

  try {
    let tx = await arweave.createTransaction({ data }, wallet);
    await arweave.transactions.sign(tx, wallet);
    await arweave.transactions.post(tx);
    await arweave.api.get('mine');

    return res.json({ status: 'posted', txid: tx.id });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`Arweave Poster running on http://localhost:${PORT}`);
});
