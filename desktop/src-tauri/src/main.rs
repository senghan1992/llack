// Hide the console window on Windows release builds — a GUI app that opens a
// terminal behind itself looks broken.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    llack_lib::run()
}
