import UIKit

class SceneDelegate: UIResponder, UIWindowSceneDelegate {

    var window: UIWindow?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
        guard let windowScene = (scene as? UIWindowScene) else { return }
        let storyboard = UIStoryboard(name: "Main", bundle: nil)
        let window = UIWindow(windowScene: windowScene)
        window.rootViewController = storyboard.instantiateInitialViewController()
        // Our own theme (light/dark) is fully controlled from JS via CSS vars +
        // StatusBar.setStyle(), independent of the phone's system setting. If we
        // leave this on .unspecified, UIKit's system dark-mode materials (used
        // during the animated status-bar-style cross-fade) follow the iPhone's
        // OS theme instead, and when that disagrees with our own theme the
        // transition blends into a gray patch instead of a clean dark bar.
        window.overrideUserInterfaceStyle = .light
        self.window = window
        window.makeKeyAndVisible()
    }
}
