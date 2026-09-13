import unittest

from phobos.scripts.forum_understanding import ForumUnderstandingEngine
from phobos.scripts.profile_analyzer import ProfileAnalyzer


PROFILE_HTML = """
<html><head><title>Shadow Forums Profile for: alice</title>
<link rel="stylesheet" href="/templates/Wasp/userinfo.css"></head><body>
<div class="user_profile"><div class="user_desc post-text">
<img class="profile_avatar" src="/!avatar/alice"><h1>alice</h1></div>
<div class="user_stat"><h1>Statistics for alice:</h1><ul>
<li>Last seen on <b>11.07.2022 11:54:22</b></li>
<li>Has written <a href="/!search/?u=alice"><b>2</b> posts</a> on the forum.</li>
</ul></div></div></body></html>
"""

THREAD_HTML = """
<html><head><title>Shadow Forums Test thread</title>
<link rel="stylesheet" href="/templates/Wasp/posts.css"></head><body>
<div class="thread_caption">Test thread</div><div class="multi_content">
<div class="post" id="10"><a class="user_name" href="/!userinfo/alice">alice</a>
<div class="last_edit">Created 10.06.2022, read: 12 times</div><div class="post_text"><article>Opening post</article></div></div>
<div class="post" id="11"><a class="user_name" href="/!userinfo/bob">bob</a>
<div class="last_edit">Created 11.06.2022, read: 8 times</div><div class="post_text"><article>Reply body</article></div></div>
</div></body></html>
"""


class ForumUnderstandingTests(unittest.TestCase):
    def setUp(self):
        self.engine = ForumUnderstandingEngine()

    def test_asmbb_profile_and_history(self):
        url = "http://example.onion/!userinfo/alice"
        result = self.engine.analyze(url, PROFILE_HTML)
        self.assertEqual("profile", result.page_type)
        self.assertEqual("alice", result.username)
        self.assertEqual("http://example.onion/!search/?u=alice", result.profile_fields["activity_url"])
        self.assertGreaterEqual(result.page_confidence, 0.58)

    def test_thread_blocks_and_canonical_identity(self):
        first = self.engine.analyze("http://example.onion/tag/test-thread.12/", THREAD_HTML)
        second = self.engine.analyze("http://example.onion/other/test-thread.12/", THREAD_HTML)
        self.assertEqual(["post", "reply"], [block.block_type for block in first.blocks])
        self.assertEqual("alice", first.blocks[0].author)
        self.assertEqual("bob", first.blocks[1].author)
        self.assertEqual(first.blocks[0].permalink, second.blocks[0].permalink)

    def test_relationship_storage(self):
        analyzer = ProfileAnalyzer(":memory:")
        analyzer.analyze_and_save("http://example.onion/tag/test-thread.12/", THREAD_HTML, "", "crawler", {})
        self.assertEqual(2, analyzer.database.execute("SELECT COUNT(*) FROM profiles").fetchone()[0])
        self.assertEqual(2, analyzer.database.execute("SELECT COUNT(*) FROM profile_activity").fetchone()[0])
        self.assertEqual(3, analyzer.database.execute("SELECT COUNT(*) FROM forum_relationships").fetchone()[0])
        analyzer.close()


if __name__ == "__main__":
    unittest.main()
