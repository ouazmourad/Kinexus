/**
 * EEG Waveform — Canvas-based scrolling 6-channel EEG visualization.
 */

class EEGChart {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.channels = 6;
        this.bufferSize = 250; // ~5 seconds at 50Hz
        this.channelColors = [
            '#3b82f6', // blue
            '#22c55e', // green
            '#ef4444', // red
            '#f97316', // orange
            '#a855f7', // purple
            '#06b6d4', // cyan
        ];
        this.channelLabels = ['Fp1', 'Fp2', 'F3', 'F4', 'C3', 'C4'];
        this.data = [];
        for (let i = 0; i < this.channels; i++) {
            this.data.push(new Float32Array(this.bufferSize).fill(0));
        }
        this._resize();
        window.addEventListener('resize', () => this._resize());
        this._draw();
    }

    _resize() {
        const rect = this.canvas.parentElement.getBoundingClientRect();
        this.canvas.width = rect.width;
        this.canvas.height = rect.height - 30;
    }

    pushData(channels) {
        // channels: array of arrays, one per channel
        if (!channels || channels.length === 0) return;
        for (let ch = 0; ch < Math.min(channels.length, this.channels); ch++) {
            const incoming = channels[ch];
            const buf = this.data[ch];
            const inLen = incoming.length;
            if (inLen >= this.bufferSize) {
                this.data[ch] = new Float32Array(incoming.slice(-this.bufferSize));
            } else {
                // Shift left and append
                const newBuf = new Float32Array(this.bufferSize);
                newBuf.set(buf.subarray(inLen));
                for (let i = 0; i < inLen; i++) {
                    newBuf[this.bufferSize - inLen + i] = incoming[i];
                }
                this.data[ch] = newBuf;
            }
        }
    }

    _draw() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;
        const chanHeight = h / this.channels;

        ctx.fillStyle = '#0a0e17';
        ctx.fillRect(0, 0, w, h);

        for (let ch = 0; ch < this.channels; ch++) {
            const yOffset = ch * chanHeight + chanHeight / 2;
            const buf = this.data[ch];

            // Grid line
            ctx.strokeStyle = '#1a2332';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(0, ch * chanHeight);
            ctx.lineTo(w, ch * chanHeight);
            ctx.stroke();

            // Channel label
            ctx.fillStyle = this.channelColors[ch];
            ctx.font = '10px JetBrains Mono, monospace';
            ctx.fillText(this.channelLabels[ch], 4, ch * chanHeight + 12);

            // Waveform
            ctx.strokeStyle = this.channelColors[ch];
            ctx.lineWidth = 1.5;
            ctx.globalAlpha = 0.85;
            ctx.beginPath();

            // Find amplitude range for normalization
            let maxAmp = 0;
            for (let i = 0; i < buf.length; i++) {
                const abs = Math.abs(buf[i]);
                if (abs > maxAmp) maxAmp = abs;
            }
            if (maxAmp === 0) maxAmp = 1;
            const scale = (chanHeight * 0.4) / maxAmp;

            for (let i = 0; i < buf.length; i++) {
                const x = (i / buf.length) * w;
                const y = yOffset - buf[i] * scale;
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
            ctx.globalAlpha = 1;
        }

        requestAnimationFrame(() => this._draw());
    }
}
