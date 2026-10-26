import whisper

model = whisper.load_model("turbo")  # l'articolo usa "turbo"
audio = whisper.pad_or_trim(whisper.load_audio("testEmy.mp3"))
mel = whisper.log_mel_spectrogram(audio, n_mels=model.dims.n_mels).to(model.device)

_, probs = model.detect_language(mel)
print("Lingua:", max(probs, key=probs.get))

result = whisper.decode(model, mel, whisper.DecodingOptions(fp16=False))
print(result.text)
