class Nerq < Formula
  desc "AI agent trust verification CLI"
  homepage "https://nerq.ai"
  url "https://files.pythonhosted.org/packages/source/n/nerq/nerq-1.0.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256"
  license "MIT"

  depends_on "python@3.11"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "Trust Score", shell_output("#{bin}/nerq check langchain 2>&1", 0)
  end
end
