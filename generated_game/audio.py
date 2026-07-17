"""
Synthesized audio feedback engine.

Generates all sounds procedurally using pygame.mixer.
No external audio files or numpy required.
"""

import math
import pygame
from typing import Optional


class AudioEngine:
    """
    Generates and manages synthesized audio feedback for the game.
    
    Produces:
    - Line-complete chord (major third interval)
    - Enemy spawn alerts (3-tone descending pattern)
    - Death buzz (descending frequency sweep)
    - Background ambience loop
    """
    
    def __init__(self) -> None:
        """Initialize the audio engine with mixer settings."""
        pygame.mixer.init(
            frequency=22050,
            size=-16,
            channels=2,
            buffer=512
        )
        pygame.mixer.set_num_channels(8)
        
        self._volume: float = 0.5
        self._background_channel: Optional[pygame.mixer.Channel] = None
        self._current_background_sound: Optional[pygame.mixer.Sound] = None
        
        # Pregenerate common sounds
        self._line_complete_sound: pygame.mixer.Sound = self._generate_line_complete()
        self._enemy_spawn_sound: pygame.mixer.Sound = self._generate_enemy_spawn()
        self._death_sound: pygame.mixer.Sound = self._generate_death()
        self._background_sound: pygame.mixer.Sound = self._generate_background()
    
    def _generate_sine_wave(
        self,
        frequency: float,
        duration: float,
        amplitude: float = 0.3,
        sample_rate: int = 22050
    ) -> list:
        """
        Generate a sine wave using pure math (no numpy).
        
        Args:
            frequency: Frequency in Hz
            duration: Duration in seconds
            amplitude: Amplitude (0.0 to 1.0)
            sample_rate: Sample rate in Hz
            
        Returns:
            List of float samples
        """
        samples: int = int(sample_rate * duration)
        wave: list = []
        
        for i in range(samples):
            t = i / sample_rate
            sample = amplitude * math.sin(2 * math.pi * frequency * t)
            wave.append(sample)
        
        # Apply fade envelope to prevent clicks
        fade_samples: int = int(sample_rate * 0.01)  # 10ms fade
        if fade_samples > 0 and samples > 2 * fade_samples:
            for i in range(fade_samples):
                fade_in_factor = i / fade_samples
                wave[i] *= fade_in_factor
            for i in range(fade_samples):
                fade_out_factor = (fade_samples - i) / fade_samples
                wave[-(i + 1)] *= fade_out_factor
        
        return wave
    
    def _generate_line_complete(self) -> pygame.mixer.Sound:
        """
        Generate a major third chord (pleasant completion sound).
        C (261.63 Hz) + E (329.63 Hz)
        """
        duration: float = 0.4
        sample_rate: int = 22050
        
        # Generate two frequencies
        c_note: list = self._generate_sine_wave(261.63, duration, 0.25, sample_rate)
        e_note: list = self._generate_sine_wave(329.63, duration, 0.25, sample_rate)
        
        # Combine
        combined: list = [c_note[i] + e_note[i] for i in range(len(c_note))]
        
        # Normalize
        max_val = max(abs(s) for s in combined) if combined else 1.0
        if max_val > 0:
            combined = [s / max_val for s in combined]
        
        # Convert to stereo int16
        stereo_int16: list = []
        for sample in combined:
            int_sample = int(sample * 32767)
            stereo_int16.append(int_sample)
            stereo_int16.append(int_sample)
        
        # Convert to bytes
        stereo_bytes = b''.join(s.to_bytes(2, 'little', signed=True) for s in stereo_int16)
        
        sound: pygame.mixer.Sound = pygame.mixer.Sound(buffer=stereo_bytes)
        sound.set_volume(self._volume)
        return sound
    
    def _generate_enemy_spawn(self) -> pygame.mixer.Sound:
        """
        Generate a 3-tone descending alert pattern.
        High-mid-low sequence with quick tempo.
        """
        duration_per_tone: float = 0.1
        gap: float = 0.05
        sample_rate: int = 22050
        
        # Three descending tones
        high: list = self._generate_sine_wave(800, duration_per_tone, 0.2, sample_rate)
        mid: list = self._generate_sine_wave(600, duration_per_tone, 0.2, sample_rate)
        low: list = self._generate_sine_wave(400, duration_per_tone, 0.2, sample_rate)
        
        # Add gaps (silence)
        gap_samples: int = int(sample_rate * gap)
        silence: list = [0.0] * gap_samples
        
        # Concatenate
        sequence: list = high + silence + mid + silence + low
        
        # Normalize
        max_val = max(abs(s) for s in sequence) if sequence else 1.0
        if max_val > 0:
            sequence = [s / max_val for s in sequence]
        
        # Convert to stereo int16
        stereo_int16: list = []
        for sample in sequence:
            int_sample = int(sample * 32767)
            stereo_int16.append(int_sample)
            stereo_int16.append(int_sample)
        
        # Convert to bytes
        stereo_bytes = b''.join(s.to_bytes(2, 'little', signed=True) for s in stereo_int16)
        
        sound: pygame.mixer.Sound = pygame.mixer.Sound(buffer=stereo_bytes)
        sound.set_volume(self._volume)
        return sound
    
    def _generate_death(self) -> pygame.mixer.Sound:
        """
        Generate a descending buzz/chirp (game over sound).
        Frequency sweep from high to low with a buzzy texture.
        """
        duration: float = 0.5
        sample_rate: int = 22050
        samples: int = int(sample_rate * duration)
        
        # Frequency sweep from 600 Hz down to 200 Hz
        freq_start: float = 600.0
        freq_end: float = 200.0
        
        wave: list = []
        phase: float = 0.0
        
        for i in range(samples):
            # Linear frequency sweep
            progress = i / samples
            freq = freq_start + (freq_end - freq_start) * progress
            
            # Instantaneous phase for frequency sweep
            phase += 2 * math.pi * freq / sample_rate
            
            # Generate buzz with harmonics
            sample = (
                0.2 * math.sin(phase) +
                0.1 * math.sin(2 * phase) +
                0.05 * math.sin(3 * phase)
            )
            wave.append(sample)
        
        # Envelope: fade in quick, fade out longer
        fade_in_samples: int = int(sample_rate * 0.02)
        fade_out_samples: int = int(sample_rate * 0.3)
        
        for i in range(fade_in_samples):
            wave[i] *= i / fade_in_samples
        
        for i in range(fade_out_samples):
            wave[-(i + 1)] *= (fade_out_samples - i) / fade_out_samples
        
        # Normalize
        max_val = max(abs(s) for s in wave) if wave else 1.0
        if max_val > 0:
            wave = [s / max_val for s in wave]
        
        # Convert to stereo int16
        stereo_int16: list = []
        for sample in wave:
            int_sample = int(sample * 32767)
            stereo_int16.append(int_sample)
            stereo_int16.append(int_sample)
        
        # Convert to bytes
        stereo_bytes = b''.join(s.to_bytes(2, 'little', signed=True) for s in stereo_int16)
        
        sound: pygame.mixer.Sound = pygame.mixer.Sound(buffer=stereo_bytes)
        sound.set_volume(self._volume)
        return sound
    
    def _generate_background(self) -> pygame.mixer.Sound:
        """
        Generate background ambience: low drone with subtle variation.
        Loopable tone at ~60 Hz (very low, subsonic-ish).
        """
        duration: float = 4.0  # Longer loop
        sample_rate: int = 22050
        
        # Generate base drone
        base: list = self._generate_sine_wave(60, duration, 0.1, sample_rate)
        
        # Add subtle modulation (slow pulsing)
        wave: list = []
        for i in range(len(base)):
            t = i / sample_rate
            modulation = 0.05 * (1 + math.sin(2 * math.pi * 0.5 * t))
            wave.append(base[i] * modulation)
        
        # Normalize
        max_val = max(abs(s) for s in wave) if wave else 1.0
        if max_val > 0:
            wave = [s / max_val for s in wave]
        
        # Convert to stereo int16
        stereo_int16: list = []
        for sample in wave:
            int_sample = int(sample * 32767)
            stereo_int16.append(int_sample)
            stereo_int16.append(int_sample)
        
        # Convert to bytes
        stereo_bytes = b''.join(s.to_bytes(2, 'little', signed=True) for s in stereo_int16)
        
        sound: pygame.mixer.Sound = pygame.mixer.Sound(buffer=stereo_bytes)
        sound.set_volume(self._volume * 0.3)  # Background is quieter
        return sound
    
    def play_line_complete(self) -> None:
        """Play the line-completion chord (success feedback)."""
        if self._line_complete_sound:
            self._line_complete_sound.play()
    
    def play_enemy_spawn(self) -> None:
        """Play the enemy spawn alert (descending 3-tone)."""
        if self._enemy_spawn_sound:
            self._enemy_spawn_sound.play()
    
    def play_death(self) -> None:
        """Play the death/game-over buzz."""
        if self._death_sound:
            self._death_sound.play()
    
    def play_background_loop(self) -> None:
        """
        Start the background ambience loop.
        Loops indefinitely.
        """
        if self._current_background_sound is None:
            if self._background_channel is None:
                self._background_channel = pygame.mixer.find_channel()
            
            if self._background_channel is not None:
                self._current_background_sound = self._background_sound
                self._background_channel.play(self._background_sound, loops=-1)
    
    def set_volume(self, level: float) -> None:
        """
        Set the master volume level.
        
        Args:
            level: Volume level (0.0 to 1.0)
        """
        self._volume = max(0.0, min(1.0, level))
        
        # Update all sound volumes
        self._line_complete_sound.set_volume(self._volume)
        self._enemy_spawn_sound.set_volume(self._volume)
        self._death_sound.set_volume(self._volume)
        self._background_sound.set_volume(self._volume * 0.3)
        
        if self._background_channel is not None:
            self._background_channel.set_volume(self._volume * 0.3)
    
    def stop_all(self) -> None:
        """Stop all audio playback."""
        pygame.mixer.stop()
        if self._background_channel is not None:
            self._background_channel.stop()
        self._current_background_sound = None
