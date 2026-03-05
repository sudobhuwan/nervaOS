"""
NervaOS Voice - Optimized with Deepgram Streaming
Real-time voice recognition with low latency
"""

import logging
import asyncio
import pyaudio
import pygame
import requests
import json
from typing import Optional
from pathlib import Path
import time
import websockets

logger = logging.getLogger('nerva-voice')

try:
    from deepgram import DeepgramClient
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DEEPGRAM_AVAILABLE = False


class NervaVoice:
    """Optimized voice with Deepgram streaming WebSocket"""
    
    def __init__(self, daemon, deepgram_key: str):
        self.daemon = daemon
        self.deepgram_key = deepgram_key
        self.enabled = False
        
        # Audio  
        self.audio = None
        self.stream = None
        pygame.mixer.init()
        
        # WebSocket
        self.ws = None
        
        # State
        self.is_awake = False
        self.wake_time = 0
        self.wake_timeout = 10
        
        # Wake words
        self.wake_words = [
            'nerva', 'nava', 'nabha', 'nova', 'nerve', 'narva',
            'nirma', 'nerf', 'nepal', 'naira', 'never', 'network'
        ]
        
    async def start(self):
        """Start optimized voice"""
        self.audio = pyaudio.PyAudio()
        self.enabled = True
        
        logger.info("✅ Voice ready - Streaming mode")
        
        # Greet
        await self.speak("NERVA voice control active. Say NERVA to wake me.")
        
        # Start streaming
        asyncio.create_task(self._stream_audio())
    
    async def _stream_audio(self):
        """Stream audio to Deepgram WebSocket"""
        try:
            # WebSocket URL
            url = "wss://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&encoding=linear16&sample_rate=16000&channels=1&interim_results=false"
            
            # Auth header (list of tuples for websockets v15)
            headers = [("Authorization", f"Token {self.deepgram_key}")]
            
            async with websockets.connect(url, additional_headers=headers) as ws:
                self.ws = ws
                logger.info("🎤 Connected to Deepgram streaming")
                
                # Start receiving transcriptions
                asyncio.create_task(self._receive_transcriptions())
                
                # Open mic and stream
                self.stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    frames_per_buffer=4096
                )
                
                # Stream audio
                while self.enabled:
                    data = self.stream.read(4096, exception_on_overflow=False)
                    await ws.send(data)
                    await asyncio.sleep(0.01)
        
        except Exception as e:
            logger.error(f"Streaming error: {e}")
        finally:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
    
    async def _receive_transcriptions(self):
        """Receive transcriptions from WebSocket"""
        try:
            while self.enabled:
                message = await self.ws.recv()
                result = json.loads(message)
                
                # Get transcript
                transcript = result.get('channel', {}).get('alternatives', [{}])[0].get('transcript', '')
                
                if transcript:
                    logger.info(f"Heard: {transcript}")
                    await self._process_transcription(transcript)
        
        except Exception as e:
            logger.error(f"Receive error: {e}")
    
    async def _process_transcription(self, text: str):
        """Process transcribed text"""
        if not text or len(text) < 2:
            return
        
        text_lower = text.lower()
        
        # Check timeout
        if self.is_awake and time.time() - self.wake_time > self.wake_timeout:
            logger.info("💤 Timeout")
            self.is_awake = False
        
        if not self.is_awake:
            # Check wake word
            if any(w in text_lower for w in self.wake_words):
                logger.info(f"⚡ Wake: {text}")
                self.is_awake = True
                self.wake_time = time.time()
                
                # Extract command
                command = text_lower
                for w in self.wake_words:
                    command = command.replace(w, '')
                command = command.strip()
                
                if command:
                    await self._execute_command(command)
                else:
                    await self.speak("Yes?")
        else:
            # Awake - execute
            logger.info(f"⚡ Command: {text}")
            await self._execute_command(text)
    
    async def _execute_command(self, command: str):
        """Execute via daemon interface (shows in chat!)"""
        try:
            logger.info(f"💬 Sending: {command}")
            
            # Use daemon interface - this processes everything properly
            if self.daemon.interface:
                response = await self.daemon.interface.AskAI(command)
                logger.info(f"✅ Response received")
                
                clean = self._clean_for_voice(response)
                await self.speak(clean)
            else:
                await self.speak("System error")
        
        except Exception as e:
            logger.error(f"Execute error: {e}", exc_info=True)
            await self.speak("Error")
    
    def _clean_for_voice(self, text: str) -> str:
        """Clean for speaking"""
        import re
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'#+\s*', '', text)
        text = re.sub(r'[^\x00-\x7F]+', '', text)
        text = re.sub(r'http[s]?://\S+', '', text)
        
        sentences = text.split('. ')
        if len(sentences) > 3:
            text = '. '.join(sentences[:3]) + '.'
        
        return text.strip()
    
    async def speak(self, text: str):
        """Speak with Deepgram TTS"""
        logger.info(f"🗣️  {text}")
        
        try:
            audio = await asyncio.get_event_loop().run_in_executor(
                None, self._deepgram_tts, text
            )
            
            if audio:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._play_audio, audio
                )
        except Exception as e:
            logger.error(f"Speak error: {e}")
    
    def _deepgram_tts(self, text: str) -> Optional[bytes]:
        """Deepgram TTS"""
        try:
            url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en"
            headers = {
                "Authorization": f"Token {self.deepgram_key}",
                "Content-Type": "application/json"
            }
            data = {"text": text}
            
            response = requests.post(url, headers=headers, json=data, timeout=10)
            
            if response.status_code == 200:
                return response.content
            return None
        except Exception as e:
            logger.error(f"TTS error: {e}")
            return None
    
    def _play_audio(self, audio_data: bytes):
        """Play audio"""
        try:
            temp_file = Path("/tmp/nerva_speech.mp3")
            temp_file.write_bytes(audio_data)
            
            pygame.mixer.music.load(str(temp_file))
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
        except Exception as e:
            logger.error(f"Play error: {e}")
    
    def stop(self):
        """Stop"""
        self.enabled = False
        if self.audio:
            self.audio.terminate()
        pygame.mixer.quit()


class NervaManager:
    """Voice manager"""
    
    def __init__(self, daemon):
        self.daemon = daemon
        self.nerva: Optional[NervaVoice] = None
        self.enabled = False
    
    async def start(self):
        """Start voice"""
        from ..core.env_loader import get_env
        env = get_env()
        
        key = env.get('DEEPGRAM_API_KEY')
        if not key:
            raise ValueError("DEEPGRAM_API_KEY required")
        
        self.nerva = NervaVoice(self.daemon, deepgram_key=key)
        await self.nerva.start()
        self.enabled = True
        logger.info("✅ Voice ready")
    
    def stop(self):
        """Stop"""
        if self.nerva:
            self.nerva.stop()
        self.enabled = False
