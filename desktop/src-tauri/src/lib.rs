// Côté Rust de HelpVA.
//
// Rust fait très peu de choses ici : il ouvre la fenêtre, affiche l'interface web (React)
// et active trois plugins officiels. Le vrai travail (conversion, métadonnées, rangement,
// licence) reste dans le moteur Python (dossiers engine/ et agent/), lancé comme « sidecar » :
// voir desktop/src/engine/sidecar.ts et desktop/README.md.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // Lancer helpva-engine.exe et lui écrire sur stdin (permissions : capabilities/default.json).
        .plugin(tauri_plugin_shell::init())
        // Fenêtres natives « Choisir un dossier » / « Choisir des fichiers ».
        .plugin(tauri_plugin_dialog::init())
        // Ouvrir un lien dans le navigateur par défaut.
        .plugin(tauri_plugin_opener::init())
        .run(tauri::generate_context!())
        .expect("erreur au lancement de HelpVA");
}
