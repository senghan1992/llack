// release 빌드에서 콘솔 창이 뜨지 않게 한다(Windows).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    llack_lib::run()
}
