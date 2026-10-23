import LocalAuthentication
import Foundation

let context = LAContext()
context.localizedCancelTitle = "Cancel"
var error: NSError?

// If --check argument passed, check if Touch ID / device owner auth is available
if CommandLine.arguments.contains("--check") {
    let can = context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error)
    exit(can ? 0 : 2)
}

guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else {
    exit(2)
}

let sema = DispatchSemaphore(value: 0)
var success = false

context.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: "Unlock Dock T(w)oo Vault") { res, err in
    success = res
    sema.signal()
}

_ = sema.wait(timeout: .distantFuture)
exit(success ? 0 : 1)
