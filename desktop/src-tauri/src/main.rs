// Empêche l'ouverture d'une console noire en plus de la fenêtre sous Windows
// (en version finale uniquement). NE PAS SUPPRIMER.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    helpva_desktop_lib::run()
}
