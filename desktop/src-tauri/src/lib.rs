// Côté Rust de HelpVA.
//
// Rust fait très peu de choses ici : il ouvre la fenêtre, affiche l'interface web (React)
// et active quatre plugins officiels. Le vrai travail (conversion, métadonnées, rangement,
// licence) reste dans le moteur Python (dossiers engine/ et agent/), lancé comme « sidecar » :
// voir desktop/src/engine/sidecar.ts et desktop/README.md.

/// Ouvre un dossier dans l'Explorateur, PAR-DESSUS HelpVA.
///
/// Pourquoi ici et pas dans le moteur Python ? Windows ne laisse passer au premier plan que les
/// fenêtres ouvertes par le programme qui est lui-même au premier plan (protection contre les
/// fenêtres qui volent le focus). Le moteur tourne en arrière-plan : l'Explorateur qu'il ouvrait
/// apparaissait DERRIÈRE HelpVA. Ouvert par la fenêtre HelpVA (celle qu'on vient de cliquer), il
/// passe devant. Seul un dossier existant est accepté : jamais un .exe ou un document.
#[tauri::command]
fn ouvrir_dossier(chemin: String) -> Result<(), String> {
    let p = std::path::Path::new(&chemin);
    if !p.is_absolute() || !p.is_dir() {
        return Err("Seul un dossier existant peut être ouvert.".into());
    }
    #[cfg(windows)]
    let programme = "explorer";
    #[cfg(target_os = "macos")]
    let programme = "open";
    #[cfg(all(unix, not(target_os = "macos")))]
    let programme = "xdg-open";
    std::process::Command::new(programme)
        .arg(p)
        .spawn()
        .map(|_| ())
        .map_err(|e| format!("Impossible d'ouvrir le dossier : {e}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![ouvrir_dossier])
        // Lancer helpva-engine.exe et lui écrire sur stdin (permissions : capabilities/default.json).
        .plugin(tauri_plugin_shell::init())
        // Fenêtres natives « Choisir un dossier » / « Choisir des fichiers ».
        .plugin(tauri_plugin_dialog::init())
        // Ouvrir un lien dans le navigateur par défaut.
        .plugin(tauri_plugin_opener::init())
        // Notification Windows quand un traitement finit (si HelpVA n'est pas au premier plan).
        .plugin(tauri_plugin_notification::init())
        .run(tauri::generate_context!())
        .expect("erreur au lancement de HelpVA");
}
