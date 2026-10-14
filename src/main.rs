slint::include_modules!();

fn main() {
    MainWindow::new()
        .expect("failed to create main window")
        .run()
        .expect("failed to run Slint event loop");
}
