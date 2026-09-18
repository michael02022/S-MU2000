# CLAP（foobar2000 / foo_midi 向け）

`S-MU2000-foobar.clap` は、foobar2000 の [foo_midi](https://github.com/stuerp/foo_midi)
で MIDI ファイルを鳴らすための別ビルド。通常の `S-MU2000.clap`（REAPER などフル機能向け、
ノートの口が A/B の 2 本 + A/D INPUT）とは口の形が違う別物として、別の ID・別の
ファイル名でビルドしてある。

```
make clap-foobar          build/S-MU2000-foobar.clap を作る
make install-clap-foobar  それを CLAP の置き場へ複製する
```

## foo_midi が CLAP に求めるもの

foo_midi の [README](https://github.com/stuerp/foo_midi/blob/main/docs/README.md) による
（[Nuked SC-55 CLAP](https://github.com/johnnovak/Nuked-SC55-CLAP) も同じ制約を満たしている）:

* Note Ports・Audio Ports の両方の extension を実装していること
* **ノートの入力ポートがちょうど 1 本、出力ポートは 0 本**
* ノートの口が MIDI dialect を名乗っていること
* **音声の入力ポートは 0 本**、出力ポートは 1 本だけ
* その出力ポートはステレオ（2 チャンネル）

通常版は 2 本のノート入力（パート 1-16 / 17-32）と、サンプリング用の A/D INPUT
（音声入力ポート 1 本）を持っているため、このままでは foo_midi のプレイヤー一覧に
出てこない。`S_MU2000_FOOBAR` を立てたビルドでは:

* ノートの入力ポートを 1 本だけ名乗る（`src/clap/plugin.cpp` の `kPorts`）。
  パート 17-32（MIDI In B）はこの版では使えない — 通常の MIDI ファイルは
  16 チャンネルに収まるので実害は無い
* 音声の入力ポートを 0 本と名乗る（`s_audio_ports` の `count`）。A/D INPUT は無し
* プラグイン ID・名前を通常版と別にする（`kPlugId` / `kPlugName`）。
  口の形が違う別物を同じ ID で名乗ると、ホストによっては混同する

中身のエンジン・画面・状態の保存は通常版と完全に同じ（`src/vst3/engine.*` を
そのまま使う）。変えたのは `src/clap/plugin.cpp` の口の宣言だけ。

## 起動待ち

MU2000 は実機と同じく、電源を入れてから MIDI を受けられるまで少しかかる
（[doc/vst3.md](vst3.md) の「起動待ち」）。REAPER などでは `activate()` から
すぐ戻り、起動中に届いた MIDI は溜めておいて、済んだ瞬間にまとめて流す
（少し遅れて聞こえるだけで、演奏中に触るぶんには気にならない）。

foo_midi はこの溜め置きを利用しない。`Startup()` から戻ったら**すぐ**
実物の MIDI を流し始め、音も要求してくる（[Players/CLAPPlayer.cpp](https://github.com/stuerp/foo_midi/blob/main/Players/CLAPPlayer.cpp)
に latency extension を問い合わせる処理も、待つ処理も無い）。そのままだと
起動が済むまでに届いた曲の頭の数百 ms が、済んだ瞬間に団子になって鳴る。

foo_midi 向けの版はこれを避けるため、`activate()` の中で起動が終わるまで
待つ（`S_MU2000_FOOBAR` のときだけ。REAPER 版は変えていない）。`activate()`
は音声スレッドではないので、ここで待っても実時間の音は落ちない。`init()` の
時点で既に起動を始めているので、実際に待つのはたいてい 1 秒に満たない。

## 置き場

foo_midi の Preferences → Playback → MIDI → Player → Paths ページで、
CLAP プラグインを探すフォルダを指定する。`make install-clap-foobar` は
`CLAP_INSTALL`（既定 `Program Files/Common Files/CLAP`）に入れるので、
そこを指すか、別のフォルダにコピーして指定する。

foo_midi はそのフォルダの `.dll` / `.clap` を再帰的に探し、対応するものを
`CLAP` という接頭辞を付けてプレイヤー一覧に足す（1 つのファイルに複数の
プラグインが入っていれば、それぞれ別項目になる）。

## ROM

ROM の探し方は通常版と同じ（[doc/vst3.md](vst3.md) の「置き場と ROM」を見よ）。
`roms.txt` を DLL の隣か `%LOCALAPPDATA%\S-MU2000\roms.txt` に置くのが楽。
