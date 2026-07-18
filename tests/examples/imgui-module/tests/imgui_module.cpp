// Public imgui module package end-to-end assertion: import-only consumption
// (imgui.core + glfw_opengl3 backend), context + font atlas + one frame,
// software-only (no window). Linux-only (see mcpp.toml).
#ifdef __linux__
import std;
import imgui.core;
import imgui.backend.glfw_opengl3;

int main() {
    auto init = &ImGui::Backend::GlfwOpenGL3::Init;
    auto shutdown = &ImGui::Backend::GlfwOpenGL3::Shutdown;
    if (init == nullptr || shutdown == nullptr) {
        return 1;
    }

    ImGuiContext* context = ImGui::CreateContext();
    if (context == nullptr) {
        return 2;
    }
    ImGui::SetCurrentContext(context);

    ImGuiIO& io = ImGui::GetIO();
    io.DisplaySize = ImVec2 { 320.0f, 240.0f };
    unsigned char* pixels = nullptr;
    int width = 0;
    int height = 0;
    io.Fonts->GetTexDataAsRGBA32(&pixels, &width, &height);
    if (pixels == nullptr || width <= 0 || height <= 0) {
        ImGui::DestroyContext(context);
        return 3;
    }

    ImGui::NewFrame();
    bool open = true;
    ImGui::Begin("mcpp-index imgui smoke", &open);
    ImGui::TextUnformatted("import imgui.core");
    ImGui::End();
    ImGui::Render();

    std::println("Dear ImGui {} module package ok", ImGui::GetVersion());
    ImGui::DestroyContext(context);
    return 0;
}
#else
int main() { return 0; }
#endif
